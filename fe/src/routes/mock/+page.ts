import { faker } from '@faker-js/faker';
import { redirect } from '@sveltejs/kit';
import { delay, http, HttpResponse } from 'msw';

const genMockComics = (number: number) =>
	faker.helpers.uniqueArray(faker.number.int, number).map((id) => {
		const page = faker.number.int({ min: 1, max: 100 });
		const name = `[${faker.person.firstName()}] ${faker.commerce.productName()}`;
		const lastViewedTime = faker.datatype.boolean() ? faker.date.past().toISOString() : null;
		return {
			id: id,
			size: faker.number.int({ min: 1000, max: 10000000 }),
			name: name,
			path: `/${id}/${name}`,
			updateTime: faker.date.past().toISOString(),
			archived: faker.datatype.boolean(0.1),
			favorited: faker.datatype.boolean(0.2),
			lastViewedTime: lastViewedTime,
			lastViewedPosition: lastViewedTime ? faker.number.int({ min: 0, max: page }) : null,
			coverPosition: faker.number.int({ min: 1, max: 100 }),
			entityUpdateTime: faker.date.past().toISOString(),
			page: page
		};
	});

async function generateImageArrayBuffer(width: number, height: number): Promise<ArrayBuffer> {
	const canvas = document.createElement('canvas');
	canvas.width = width;
	canvas.height = height;

	const ctx = canvas.getContext('2d');
	if (!ctx) {
		throw new Error('Failed to get canvas context');
	}

	ctx.fillStyle = '#ffffff';
	ctx.fillRect(0, 0, width, height);

	ctx.fillStyle = '#000000';
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';

	const fontSize = Math.min(Math.max(height / 4, 10), 100) / 2;
	ctx.font = `${fontSize}px Arial`;
	ctx.fillText(`${width}x${height}`, width / 2, height / 2);

	return new Promise((resolve) => {
		canvas.toBlob(async (blob) => {
			const arrayBuffer = await blob?.arrayBuffer();
			if (!arrayBuffer) {
				throw new Error('Failed to convert canvas to ArrayBuffer');
			}
			resolve(arrayBuffer);
		}, 'image/png');
	});
}

async function msw() {
	const comics = genMockComics(100);

	const findComic = (id: string | readonly string[] | undefined) =>
		id !== undefined ? comics.find((c) => c.id === Number(id)) : undefined;

	const handlers = [
		// --- Comics list ---
		http.get('/api/comics', async ({ request }) => {
			await delay(1000);
			const url = new URL(request.url);
			const top = url.searchParams.get('top');
			if (top) {
				return HttpResponse.json(comics.slice(0, Number(top)));
			}
			return HttpResponse.json(comics);
		}),

		// --- Single comic ---
		http.get('/api/comics/:id', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			return HttpResponse.json(comic);
		}),

		// --- Delete comic ---
		http.delete('/api/comics/:id', async ({ request, params }) => {
			await delay(500);
			const url = new URL(request.url);
			const permanent = url.searchParams.get('permanent');
			const id = Number(params.id);
			const index = comics.findIndex((c) => c.id === id);
			if (index === -1) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			if (permanent === 'true') {
				comics.splice(index, 1);
			} else {
				comics[index].archived = true;
			}
			return HttpResponse.json({ msg: 'Deleted' });
		}),

		// --- Favor ---
		http.post('/api/comics/:id/favor', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.favorited = true;
			return HttpResponse.json({ favorited: true });
		}),

		// --- Unfavor ---
		http.delete('/api/comics/:id/favor', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.favorited = false;
			return HttpResponse.json({ favorited: false });
		}),

		// --- Refresh ---
		http.post('/api/comics/:id/refresh', async ({ params }) => {
			await delay(800);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.entityUpdateTime = new Date().toISOString();
			return HttpResponse.json(comic);
		}),

		// --- Rename ---
		http.post('/api/comics/:id/rename', async ({ params, request }) => {
			await delay(400);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const body = (await request.json()) as { name: string };
			comic.name = body.name;
			return HttpResponse.json({ name: body.name });
		}),

		// --- Detail (page list) ---
		http.post('/api/comics/:id/detail', async ({ params }) => {
			await delay(600);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const pageDetails = Array.from({ length: comic.page }, (_, i) => ({
				name: `page_${String(i + 1).padStart(3, '0')}.jpg`
			}));
			return HttpResponse.json({ pageDetails });
		}),

		// --- Like page ---
		http.post('/api/comics/:id/:page/like', async () => {
			await delay(200);
			return HttpResponse.json({ msg: 'Liked' });
		}),

		// --- Set cover ---
		http.post('/api/comics/:id/:page/cover', async ({ params }) => {
			await delay(200);
			const comic = findComic(params.id);
			if (comic) comic.coverPosition = Number(params.page);
			return HttpResponse.json({ msg: 'Cover set' });
		}),

		// --- Comic page image ---
		http.get('/api/comics/:id/:page', async () => {
			const width = faker.number.int({ min: 100, max: 1000 });
			const height = faker.number.int({ min: 100, max: 1000 });
			const arrayBuf = await generateImageArrayBuffer(width, height);
			return HttpResponse.arrayBuffer(arrayBuf);
		}),

		// --- Cover images ---
		http.get('/comics/*', async () => {
			const width = faker.number.int({ min: 100, max: 1000 });
			const height = faker.number.int({ min: 100, max: 1000 });
			const arrayBuf = await generateImageArrayBuffer(width, height);
			return HttpResponse.arrayBuffer(arrayBuf);
		}),

		// --- Videos / Images (not implemented) ---
		http.get('/api/videos', async () => {
			await delay(1000);
			return HttpResponse.text('Error: Not Implemented', { status: 501 });
		}),
		http.get('/api/images', async () => {
			await delay(1000);
			return HttpResponse.text('Error: Not Implemented', { status: 501 });
		})
	];

	const { setupWorker } = await import('msw/browser');
	const worker = setupWorker(...handlers);
	await worker.start({
		onUnhandledRequest: 'bypass'
	});
}

export async function load() {
	await msw();
	redirect(302, '/');
}
