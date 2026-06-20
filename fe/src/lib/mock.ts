import { faker } from '@faker-js/faker';
import { delay, http, HttpResponse } from 'msw';
import { authState } from '$lib/auth.svelte';

const genMockComics = (number: number) =>
	faker.helpers.uniqueArray(faker.number.int, number).map((id) => {
		const page = faker.number.int({ min: 1, max: 100 });
		const author = faker.person.firstName();
		const name = `[${author}] ${faker.commerce.productName()}`;
		const lastViewedTime = faker.datatype.boolean() ? faker.date.past().toISOString() : null;
		return {
			id,
			size: faker.number.int({ min: 1000, max: 10000000 }),
			name,
			// group by author so the folder view has a natural tree (faker's
			// limited name pool means several authors get multiple works)
			path: `/data/comics/${author}/${name}`,
			updateTime: faker.date.past().toISOString(),
			archived: faker.datatype.boolean(0.1),
			favorited: faker.datatype.boolean(0.2),
			missing: faker.datatype.boolean(0.1),
			lastViewedTime,
			lastViewedPosition: lastViewedTime ? faker.number.int({ min: 0, max: page }) : null,
			coverPosition: faker.number.int({ min: 1, max: 100 }),
			entityUpdateTime: faker.date.past().toISOString(),
			page
		};
	});

async function generateImageArrayBuffer(width: number, height: number): Promise<ArrayBuffer> {
	const canvas = document.createElement('canvas');
	canvas.width = width;
	canvas.height = height;
	const ctx = canvas.getContext('2d')!;
	ctx.fillStyle = '#ffffff';
	ctx.fillRect(0, 0, width, height);
	ctx.fillStyle = '#000000';
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';
	const fontSize = Math.min(Math.max(height / 4, 10), 100) / 2;
	ctx.font = `${fontSize}px Arial`;
	ctx.fillText(`${width}x${height}`, width / 2, height / 2);
	return new Promise((resolve) => {
		canvas.toBlob(async (blob) => resolve((await blob!.arrayBuffer())!), 'image/png');
	});
}

export async function setupMock(authRequired: boolean) {
	console.log('Setting up mock...');
	authState.required = authRequired;

	const comics = genMockComics(100);
	// The backend skips folder-size computation at scan time (size stays 0
	// until the refresh endpoint fills it) — mirror that for image folders.
	const images = genMockComics(24).map((i) => ({ ...i, size: 0 }));
	const findComic = (id: string | readonly string[] | undefined) =>
		id !== undefined ? comics.find((c) => c.id === Number(id)) : undefined;
	const findImage = (id: string | readonly string[] | undefined) =>
		id !== undefined ? images.find((c) => c.id === Number(id)) : undefined;

	// Mock scan state — `triggerScan` kicks off a short fake run that the
	// admin page's polling watches progress through (mirrors the real
	// running -> phases -> finished lifecycle, including open-timing metrics).
	const scanState = {
		running: false,
		startedAt: null as string | null,
		finishedAt: null as string | null,
		processed: 0,
		total: 0,
		startMs: 0
	};

	const handlers = [
		http.get('/api/system/scan', async () => {
			if (scanState.running) {
				scanState.processed = Math.min(scanState.total, scanState.processed + 7);
				if (scanState.processed >= scanState.total) {
					scanState.running = false;
					scanState.finishedAt = new Date().toISOString();
				}
			}
			const count = scanState.processed;
			const durations = Array.from({ length: count }, () =>
				faker.number.float({ min: 5, max: 900 })
			);
			const sorted = [...durations].sort((a, b) => a - b);
			const avg = count ? durations.reduce((a, b) => a + b, 0) / count : 0;
			const p95 = count ? sorted[Math.min(count - 1, Math.floor(count * 0.95))] : 0;
			const slowest = [...durations]
				.sort((a, b) => b - a)
				.slice(0, 10)
				.map((ms, i) => ({ path: `/data/comics/slow-${i}.zip`, ms: Math.round(ms * 10) / 10 }));
			const duration = scanState.startMs
				? Math.round(
						((scanState.finishedAt ? Date.parse(scanState.finishedAt) : Date.now()) -
							scanState.startMs) /
							100
					) / 10
				: null;
			return HttpResponse.json({
				running: scanState.running,
				media_type: scanState.startedAt ? 'all' : null,
				phase: scanState.running ? 'comics' : null,
				total: scanState.total,
				processed: scanState.processed,
				reconciled: scanState.startedAt ? 3 : 0,
				started_at: scanState.startedAt,
				finished_at: scanState.finishedAt,
				duration_seconds: duration,
				timing: {
					count,
					avg_ms: Math.round(avg * 10) / 10,
					p95_ms: Math.round(p95 * 10) / 10,
					slowest
				},
				last_result: scanState.finishedAt ? { status: 'success', comics: 'done' } : null
			});
		}),
		http.post('/api/system/scan', async () => {
			await delay(200);
			if (scanState.running) {
				return HttpResponse.json({
					status: 'already_running',
					message: 'A scan is already in progress'
				});
			}
			scanState.running = true;
			scanState.startedAt = new Date().toISOString();
			scanState.finishedAt = null;
			scanState.processed = 0;
			scanState.total = 100;
			scanState.startMs = Date.now();
			return HttpResponse.json({ status: 'started', message: 'Scan started for: all' });
		}),
		http.get('/api/system/tasks', async () => {
			await delay(200);
			const next = new Date();
			next.setHours(2, 0, 0, 0);
			if (next.getTime() <= Date.now()) next.setDate(next.getDate() + 1);
			return HttpResponse.json({
				daily_scan: { scan_hour: 2, next_run: next.toISOString() },
				backup: {
					last_backup: faker.date.recent().toISOString(),
					backup_count: 7,
					cadence_hours: 24
				}
			});
		}),
		http.get('/api/auth/status', async () => {
			await delay(100);
			return HttpResponse.json({ required: authState.required });
		}),
		http.post('/api/auth/login', async ({ request }) => {
			await delay(300);
			const body = (await request.json()) as { password?: string };
			if (body.password === 'mock') return HttpResponse.json({ token: 'mock-token-for-testing' });
			return HttpResponse.json({ detail: 'Invalid password' }, { status: 401 });
		}),
		http.get('/api/comics', async ({ request }) => {
			await delay(1000);
			const params = new URL(request.url).searchParams;
			const fileMiss = params.get('fileMiss') === 'true';
			// Mirror the backend: fileMiss=true returns the gone files (organize
			// page); the default list hides them.
			const filtered = comics.filter((c) => Boolean(c.missing) === fileMiss);
			const top = params.get('top');
			return HttpResponse.json(top ? filtered.slice(0, Number(top)) : filtered);
		}),
		http.post('/api/comics/check', async ({ request }) => {
			await delay(600);
			const body = (await request.json()) as { ids: number[] };
			// Mirror the backend tri-state: a recovered file clears `missing`, a
			// confirmed-gone file sets it, and a flaky-mount blip (unknown) leaves
			// the flag untouched. Demo: ~70% recover, ~15% unknown, rest stay gone.
			const results = body.ids.map((id) => {
				const comic = comics.find((c) => c.id === id);
				if (!comic) return { id, status: 'notfound' };
				const roll = faker.number.float();
				if (roll < 0.7) {
					comic.missing = false;
					return { id, status: 'present' };
				}
				if (roll < 0.85) return { id, status: 'unknown' };
				comic.missing = true;
				return { id, status: 'absent' };
			});
			return HttpResponse.json({ results });
		}),
		http.get('/api/comics/:id', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			return HttpResponse.json(comic);
		}),
		http.delete('/api/comics/:id', async ({ request, params }) => {
			await delay(500);
			const permanent = new URL(request.url).searchParams.get('permanent');
			const idx = comics.findIndex((c) => c.id === Number(params.id));
			if (idx === -1) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			if (permanent === 'true') comics.splice(idx, 1);
			else comics[idx].archived = true;
			return HttpResponse.json({ msg: 'Deleted' });
		}),
		http.post('/api/comics/:id/favor', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.favorited = true;
			return HttpResponse.json({ favorited: true });
		}),
		http.delete('/api/comics/:id/favor', async ({ params }) => {
			await delay(300);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.favorited = false;
			return HttpResponse.json({ favorited: false });
		}),
		http.post('/api/comics/:id/refresh', async ({ params }) => {
			await delay(800);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			comic.entityUpdateTime = new Date().toISOString();
			return HttpResponse.json(comic);
		}),
		http.post('/api/comics/:id/rename', async ({ params, request }) => {
			await delay(400);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const body = (await request.json()) as { name: string };
			comic.name = body.name;
			return HttpResponse.json({ name: body.name });
		}),
		http.get('/api/comics/:id/detail', async ({ params }) => {
			await delay(600);
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const pageDetails = Array.from({ length: comic.page }, (_, i) => ({
				name: `page_${String(i + 1).padStart(3, '0')}.jpg`
			}));
			return HttpResponse.json({ pageDetails });
		}),
		http.put('/api/comics/:id/progress', async ({ params, request }) => {
			const comic = findComic(params.id);
			if (!comic) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const body = (await request.json()) as { position: number };
			comic.lastViewedPosition = body.position;
			comic.lastViewedTime = new Date().toISOString();
			return HttpResponse.json({ position: body.position, lastViewedTime: comic.lastViewedTime });
		}),
		http.post('/api/comics/:id/pages/:page/like', async () => {
			await delay(200);
			return HttpResponse.json({ msg: 'Liked' });
		}),
		http.post('/api/comics/:id/pages/:page/cover', async ({ params }) => {
			await delay(200);
			const comic = findComic(params.id);
			if (comic) {
				comic.coverPosition = Number(params.page);
				// Mirror the backend: regenerating the cover bumps entityUpdateTime,
				// which the frontend uses as the cover URL's cache-busting token.
				comic.entityUpdateTime = new Date().toISOString();
			}
			return HttpResponse.json({ msg: 'Cover set' });
		}),
		http.get('/api/comics/:id/pages/:page', async () => {
			const w = faker.number.int({ min: 100, max: 1000 });
			const h = faker.number.int({ min: 100, max: 1000 });
			return HttpResponse.arrayBuffer(await generateImageArrayBuffer(w, h));
		}),
		http.get('/comics/*', async () => {
			const w = faker.number.int({ min: 100, max: 1000 });
			const h = faker.number.int({ min: 100, max: 1000 });
			return HttpResponse.arrayBuffer(await generateImageArrayBuffer(w, h));
		}),
		http.get('/api/videos', async () => {
			await delay(1000);
			return HttpResponse.text('Error: Not Implemented', { status: 501 });
		}),
		http.get('/api/videos/:id', async () => {
			return HttpResponse.text('Error: Not Implemented', { status: 501 });
		}),
		http.delete('/api/videos/:id', async () => {
			return HttpResponse.text('Error: Not Implemented', { status: 501 });
		}),
		http.get('/api/images', async ({ request }) => {
			await delay(800);
			const top = new URL(request.url).searchParams.get('top');
			return HttpResponse.json(top ? images.slice(0, Number(top)) : images);
		}),
		http.get('/api/images/:id', async ({ params }) => {
			await delay(300);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			return HttpResponse.json(image);
		}),
		http.get('/api/images/:id/detail', async ({ params }) => {
			await delay(600);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const pageDetails = Array.from({ length: image.page }, (_, i) => ({
				name: `image_${String(i + 1).padStart(3, '0')}.jpg`
			}));
			return HttpResponse.json({ pageDetails });
		}),
		http.delete('/api/images/:id', async ({ params }) => {
			await delay(500);
			const idx = images.findIndex((c) => c.id === Number(params.id));
			if (idx === -1) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			images.splice(idx, 1);
			return HttpResponse.json({ msg: 'Deleted' });
		}),
		http.delete('/api/images/:id/pages/:page', async ({ params }) => {
			await delay(400);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const page = Number(params.page);
			if (page < 1 || page > image.page) {
				return HttpResponse.json({ msg: 'Page not found' }, { status: 404 });
			}
			// Mirror the backend: drop one image and bump the cover cache-bust token.
			image.page = Math.max(0, image.page - 1);
			image.entityUpdateTime = new Date().toISOString();
			return HttpResponse.json(image);
		}),
		http.post('/api/images/:id/refresh', async ({ params }) => {
			await delay(800);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			image.size = faker.number.int({ min: 1000, max: 10000000 });
			image.entityUpdateTime = new Date().toISOString();
			return HttpResponse.json(image);
		}),
		http.post('/api/images/:id/convert', async ({ params }) => {
			await delay(1200);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			// Mirror the backend: a new comic is created from the album's images
			// (named after the resulting zip file) and added to the comic library.
			const newComic = {
				...image,
				id: Math.max(0, ...comics.map((c) => c.id)) + 1,
				name: `${image.name}.zip`,
				path: `/data/comics/${image.name}.zip`,
				archived: false,
				entityUpdateTime: new Date().toISOString()
			};
			comics.push(newComic);
			return HttpResponse.json(newComic);
		}),
		http.put('/api/images/:id/progress', async ({ params, request }) => {
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const body = (await request.json()) as { position: number };
			image.lastViewedPosition = body.position;
			image.lastViewedTime = new Date().toISOString();
			return HttpResponse.json({ position: body.position, lastViewedTime: image.lastViewedTime });
		}),
		http.get('/api/images/:id/pages/:page', async () => {
			const w = faker.number.int({ min: 100, max: 1000 });
			const h = faker.number.int({ min: 100, max: 1000 });
			return HttpResponse.arrayBuffer(await generateImageArrayBuffer(w, h));
		}),
		http.get('/images/*', async () => {
			const w = faker.number.int({ min: 100, max: 1000 });
			const h = faker.number.int({ min: 100, max: 1000 });
			return HttpResponse.arrayBuffer(await generateImageArrayBuffer(w, h));
		})
	];

	const { setupWorker } = await import('msw/browser');
	const worker = setupWorker(...handlers);
	await worker.start({ onUnhandledRequest: 'bypass' });
}
