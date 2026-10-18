import { faker } from '@faker-js/faker';
import { delay, http, HttpResponse } from 'msw';
import { authState } from '$lib/auth.svelte';

// Real libraries often name author folders after the circle too, e.g.
// "[Circle Name (Author)] 作品集": give some authors a long folder name like
// that so the folder view's layout gets exercised.
const authorFolders = new Map<string, string>();
const authorFolder = (author: string) => {
	let folder = authorFolders.get(author);
	if (!folder) {
		folder = faker.datatype.boolean(0.4)
			? `[${faker.company.name()} (${author})] ${faker.helpers.arrayElement(['作品集', 'Collection', '同人誌まとめ 2019-2024'])}`
			: author;
		authorFolders.set(author, folder);
	}
	return folder;
};

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
			path: `/data/comics/${authorFolder(author)}/${name}`,
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
	// Leave a third unsorted in an inbox on another "share", so the move page has
	// comics to gather (and some cross-drive copies to warn about).
	comics.forEach((c, i) => {
		if (i % 3 === 0) c.path = `/data/comics/inbox/${c.name}`;
	});
	// Seed duplicates for the duplicate finder: re-tag a few comics as other
	// releases of the same work (different group/edition tags and archive type).
	const releaseTags = ['[汉化组] ', '(C99) ', '【DL版】', '[Scan] '];
	for (const original of comics.slice(0, 8)) {
		const title = original.name.replace(/^\[[^\]]*\]\s*/, '');
		const copies = faker.number.int({ min: 1, max: 2 });
		for (let i = 0; i < copies; i++) {
			const name = `${faker.helpers.arrayElement(releaseTags)}${title} [${faker.helpers.arrayElement(['DL版', '無修正', 'v2'])}].${faker.helpers.arrayElement(['zip', 'rar', 'cbz'])}`;
			comics.push({
				...original,
				id: Math.max(...comics.map((c) => c.id)) + 1,
				name,
				path: `/data/comics/dup/${name}`,
				size: faker.number.int({ min: 1000, max: 10000000 }),
				page: Math.max(1, original.page + faker.number.int({ min: -2, max: 2 })),
				archived: false,
				missing: false,
				favorited: false
			});
		}
	}
	// Similar (not exact) copies: a subtitle appended to the title. The last one
	// has double the pages, so the page-count warning shows up too.
	for (const [i, original] of comics.slice(8, 11).entries()) {
		const title = original.name.replace(/^\[[^\]]*\]\s*/, '');
		const name = `[Scan] ${title} Special Edition.zip`;
		comics.push({
			...original,
			id: Math.max(...comics.map((c) => c.id)) + 1,
			name,
			path: `/data/comics/dup/${name}`,
			size: faker.number.int({ min: 1000, max: 10000000 }),
			page: i === 2 ? original.page * 2 : original.page,
			archived: false,
			missing: false,
			favorited: false
		});
	}
	// Rough stand-in for the backend's filename normalization: drop bracketed
	// tags, extension, case and punctuation (no fuzzy matching in mock mode).
	const duplicateKey = (name: string) =>
		name
			.normalize('NFKC')
			.replace(/\.(zip|rar|cbz|cbr|7z|pdf)$/i, '')
			.replace(/\[[^\]]*\]|\([^)]*\)|【[^】]*】|\{[^}]*\}/g, ' ')
			.toLowerCase()
			.replace(/[\W_]+/gu, '');
	// The backend skips folder-size computation at scan time (size stays 0
	// until the refresh endpoint fills it) — mirror that for image folders.
	// Albums have no favorites or custom covers (the cover is always page 1).
	const images = genMockComics(24).map((i) => ({
		...i,
		size: 0,
		favorited: false,
		coverPosition: 0
	}));
	// Per-month mock activity for /api/comics/stats, filled lazily so
	// switching ranges keeps the same numbers.
	const mockMonthStats = new Map<
		string,
		{ added: number; read: number; readDays: number; deleted: number; deletedSize: number }
	>();
	// Stable per page, so revisiting a page shows the same numbers. Every 7th
	// page is a low-resolution PNG, to show what an odd page looks like.
	const mockPageInfo = (id: number, page: number) =>
		(id + page) % 7 === 0
			? { width: 800, height: 1131, format: 'PNG' }
			: { width: 1600 + (id % 3) * 200, height: 2400 + (id % 3) * 300, format: 'JPEG' };
	const findComic = (id: string | readonly string[] | undefined) =>
		id !== undefined ? comics.find((c) => c.id === Number(id)) : undefined;
	const findImage = (id: string | readonly string[] | undefined) =>
		id !== undefined ? images.find((c) => c.id === Number(id)) : undefined;

	// Mock scan state — a queued scan job starts a short fake run that the
	// admin page's polling watches progress through (mirrors the real
	// running -> phases -> finished lifecycle, including open-timing metrics).
	const scanState = {
		running: false,
		mediaType: 'all',
		startedAt: null as string | null,
		finishedAt: null as string | null,
		processed: 0,
		total: 0,
		startMs: 0
	};

	// Mock cover regeneration — same fake-progress pattern as the scan; a
	// couple of comics fail so the admin page's failure list has content.
	const coverState = {
		running: false,
		cancelled: false,
		cancelRequested: false,
		mode: null as string | null,
		total: 0,
		processed: 0,
		failures: [] as { id: number; name: string; reason: string }[],
		startedAt: null as string | null,
		finishedAt: null as string | null
	};

	// Mock heavy-job queue (core/jobs.py): one job runs at a time, identical
	// waiting jobs are deduped, finished ones go to a short history.
	type MockJob = {
		id: number;
		kind: 'scan' | 'covers' | 'move';
		params: Record<string, string>;
		state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
		created_at: string;
		started_at: string | null;
		finished_at: string | null;
		error: string | null;
		cancellable: boolean;
	};
	const jobQueue = {
		nextId: 1,
		running: null as MockJob | null,
		queued: [] as MockJob[],
		history: [] as MockJob[]
	};
	// Mock comic move (mover.py): takes a couple of seconds, then the records
	// point at the target folder.
	const moveState = { until: 0 };
	const finishMove = (job: MockJob) => {
		const ids = new Set(job.params.ids.split(',').map(Number));
		for (const c of comics) {
			if (ids.has(c.id)) c.path = `${job.params.target}/${c.path.split('/').pop()}`;
		}
	};
	const startJob = (job: MockJob) => {
		job.state = 'running';
		job.started_at = new Date().toISOString();
		job.cancellable = job.kind === 'covers';
		jobQueue.running = job;
		if (job.kind === 'move') {
			moveState.until = Date.now() + 2000;
			return;
		}
		if (job.kind === 'scan') {
			Object.assign(scanState, {
				running: true,
				mediaType: job.params.media_type,
				startedAt: job.started_at,
				finishedAt: null,
				processed: 0,
				total: 100,
				startMs: Date.now()
			});
			return;
		}
		const mode = job.params.mode;
		// Mock covers are all "present" except a handful, so missing mode
		// processes a short run.
		const live = comics.filter((c) => !c.archived && !c.missing).slice(mode === 'missing' ? -6 : 0);
		Object.assign(coverState, {
			running: true,
			cancelled: false,
			cancelRequested: false,
			mode,
			total: live.length,
			processed: 0,
			failures: live.slice(-2).map((c, i) => ({
				id: c.id,
				name: c.name,
				reason: i === 0 ? 'No page could be rendered as a cover' : 'Bad CRC-32 for file 001.jpg'
			})),
			startedAt: job.started_at,
			finishedAt: null
		});
	};
	// Move a finished job to history and start the next one.
	const tickJobs = () => {
		const job = jobQueue.running;
		if (job) {
			const busy =
				job.kind === 'scan'
					? scanState.running
					: job.kind === 'move'
						? Date.now() < moveState.until
						: coverState.running;
			if (busy) return;
			if (job.kind === 'move') finishMove(job);
			// A partly failed scan fails its job, as _scan_job raises on it.
			const scanFailed = job.kind === 'scan' && scanState.mediaType === 'all';
			job.state =
				job.kind === 'covers' && coverState.cancelled
					? 'cancelled'
					: scanFailed
						? 'failed'
						: 'succeeded';
			if (scanFailed) job.error = 'images: [Errno 5] Input/output error';
			job.finished_at = new Date().toISOString();
			job.cancellable = false;
			jobQueue.history = [job, ...jobQueue.history].slice(0, 20);
			jobQueue.running = null;
		}
		const next = jobQueue.queued.shift();
		if (next) startJob(next);
	};
	// A full scan / full cover run covers a narrower one (api/system.py).
	const subsumes = (
		kind: MockJob['kind'],
		a: Record<string, string>,
		b: Record<string, string>
	) => {
		if (kind === 'move') return a.ids === b.ids && a.target === b.target;
		const key = kind === 'scan' ? 'media_type' : 'mode';
		return a[key] === 'all' || a[key] === b[key];
	};
	const enqueueJob = (kind: MockJob['kind'], params: Record<string, string>) => {
		tickJobs();
		const covered = (j: MockJob) => j.kind === kind && subsumes(kind, j.params, params);
		if (jobQueue.queued.some(covered)) return 'already_queued' as const;
		const job: MockJob = {
			id: jobQueue.nextId++,
			kind,
			params,
			state: 'queued',
			created_at: new Date().toISOString(),
			started_at: null,
			finished_at: null,
			error: null,
			cancellable: true
		};
		if (jobQueue.running) {
			// Waiting jobs this one covers are replaced; it takes the first one's place.
			const replaces = (j: MockJob) => j.kind === kind && subsumes(kind, params, j.params);
			const at = jobQueue.queued.findIndex(replaces);
			if (at === -1) {
				jobQueue.queued.push(job);
			} else {
				const now = new Date().toISOString();
				for (const old of jobQueue.queued.filter(replaces)) {
					Object.assign(old, {
						state: 'cancelled',
						error: `Replaced by job #${job.id}`,
						finished_at: now,
						cancellable: false
					});
					jobQueue.history = [old, ...jobQueue.history].slice(0, 20);
				}
				jobQueue.queued = jobQueue.queued.filter((j) => !replaces(j));
				jobQueue.queued.splice(at, 0, job);
			}
			return 'queued' as const;
		}
		startJob(job);
		return 'started' as const;
	};
	const queueMessage = (status: 'started' | 'queued' | 'already_queued', what: string) =>
		({
			started: `${what} started`,
			queued: `${what} queued behind the running job`,
			already_queued: `${what} is already covered by a job waiting in the queue`
		})[status];

	// Mirrors mover.plan: the top folder under /data/comics stands for the
	// drive/share, so moving out of "inbox" counts as a cross-drive copy.
	const planMove = (ids: number[], rawTarget: string) => {
		const target = rawTarget.trim().replace(/\/+$/, '');
		if (!target.startsWith('/')) return { msg: 'Target must be an absolute folder path' };
		if (!target.startsWith('/data/comics/'))
			return { msg: 'Target must be inside a comic scan folder (/data/comics)' };
		const share = (p: string) => p.split('/')[3];
		const taken = new Set<string>();
		const items = [...new Set(ids)].map((id) => {
			const c = comics.find((x) => x.id === id);
			if (!c) return { id, name: '', source: '', destination: '', status: 'notfound' as const };
			const destination = `${target}/${c.path.split('/').pop()}`;
			const item = {
				id,
				name: c.name,
				source: c.path,
				destination,
				status: 'move' as 'move' | 'same' | 'conflict' | 'missing',
				crossDevice: false,
				reason: null as string | null
			};
			if (c.missing) item.status = 'missing';
			else if (c.path.slice(0, c.path.lastIndexOf('/')) === target) item.status = 'same';
			else if (taken.has(destination)) {
				item.status = 'conflict';
				item.reason = 'Another selected comic has the same name';
			} else if (comics.some((x) => x.path === destination)) {
				item.status = 'conflict';
				item.reason = 'A file with this name is already there';
			}
			if (item.status === 'move') {
				taken.add(destination);
				item.crossDevice = share(c.path) !== share(target);
			}
			return item;
		});
		return { target, items };
	};

	// Mock tag classification (api/tags.py), seeded with a few authors, noise
	// tags and an alias so the grouped views have content.
	type TagRow = {
		name: string;
		kind: 'author' | 'language' | 'ignored' | null;
		canonical: string | null;
		updateTime: string;
	};
	const now = () => new Date().toISOString();
	const tags = new Map<string, TagRow>();
	const seedTag = (name: string, kind: TagRow['kind'], canonical: string | null = null) =>
		tags.set(name, { name, kind, canonical, updateTime: now() });
	const mockAuthors = [...new Set(comics.map((c) => c.name.match(/^\[([^\]]+)\]/)?.[1]))]
		.filter((a): a is string => !!a && /^[A-Z][a-z]+$/.test(a))
		.slice(0, 6);
	mockAuthors.forEach((a) => seedTag(a, 'author'));
	['DL版', '無修正', 'v2', 'Scan', '汉化组', '.zip', '.rar', '.cbz'].forEach((t) =>
		seedTag(t, 'ignored')
	);
	// An alias: one more comic of the second author is released under a
	// "romanized" name, which is merged into the author.
	const aliased = comics.find((c) => mockAuthors[1] && c.name.startsWith(`[${mockAuthors[1]}]`));
	if (aliased) {
		const alias = `${mockAuthors[1]} EN`;
		const name = `[${alias}] ${faker.commerce.productName()} [English]`;
		comics.push({
			...aliased,
			id: Math.max(...comics.map((c) => c.id)) + 1,
			name,
			path: `/data/comics/inbox/${name}`
		});
		seedTag(alias, null, mockAuthors[1]);
		seedTag('English', 'language');
	}
	const tagRows = () => [...tags.values()].sort((a, b) => a.name.localeCompare(b.name));

	const handlers = [
		http.get('/api/system/jobs', async () => {
			await delay(100);
			tickJobs();
			return HttpResponse.json({
				running: jobQueue.running,
				queued: jobQueue.queued,
				history: jobQueue.history
			});
		}),
		http.delete('/api/system/jobs/:id', async ({ params }) => {
			await delay(150);
			const id = Number(params.id);
			const idx = jobQueue.queued.findIndex((j) => j.id === id);
			if (idx !== -1) {
				const [job] = jobQueue.queued.splice(idx, 1);
				Object.assign(job, {
					state: 'cancelled',
					finished_at: new Date().toISOString(),
					cancellable: false
				});
				jobQueue.history = [job, ...jobQueue.history].slice(0, 20);
				return HttpResponse.json({ status: 'cancelled' });
			}
			const running = jobQueue.running;
			if (!running || running.id !== id) {
				return HttpResponse.json({ msg: 'No queued or running job with that id' }, { status: 404 });
			}
			if (running.kind !== 'covers') {
				return HttpResponse.json(
					{ msg: "This job can't be cancelled while it runs" },
					{ status: 400 }
				);
			}
			coverState.cancelRequested = true;
			running.cancellable = false;
			return HttpResponse.json({ status: 'cancelling' });
		}),
		http.get('/api/system/covers', async () => {
			if (coverState.running && coverState.cancelRequested) {
				coverState.running = false;
				coverState.cancelled = true;
				coverState.finishedAt = new Date().toISOString();
			}
			if (coverState.running) {
				coverState.processed = Math.min(coverState.total, coverState.processed + 9);
				if (coverState.processed >= coverState.total) {
					coverState.running = false;
					coverState.finishedAt = new Date().toISOString();
					const now = new Date().toISOString();
					for (const c of comics) c.entityUpdateTime = now;
				}
			}
			tickJobs();
			const failures = coverState.failures.filter(
				(_, i) => coverState.processed >= ((i + 1) * coverState.total) / 3
			);
			return HttpResponse.json({
				running: coverState.running,
				cancelled: coverState.cancelled,
				mode: coverState.mode,
				total: coverState.total,
				processed: coverState.processed,
				failed: failures.length,
				failures,
				started_at: coverState.startedAt,
				finished_at: coverState.finishedAt
			});
		}),
		http.post('/api/system/covers', async ({ request }) => {
			await delay(200);
			const mode = new URL(request.url).searchParams.get('mode') ?? 'all';
			if (mode !== 'all' && mode !== 'missing') {
				return HttpResponse.json({ msg: 'Invalid mode' }, { status: 400 });
			}
			const status = enqueueJob('covers', { mode });
			const what = mode === 'missing' ? 'Missing cover generation' : 'Cover regeneration';
			return HttpResponse.json({ status, message: queueMessage(status, what) });
		}),
		http.get('/api/system/scan', async () => {
			if (scanState.running) {
				scanState.processed = Math.min(scanState.total, scanState.processed + 7);
				if (scanState.processed >= scanState.total) {
					scanState.running = false;
					scanState.finishedAt = new Date().toISOString();
				}
			}
			tickJobs();
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
				media_type: scanState.startedAt ? scanState.mediaType : null,
				phase: scanState.running
					? scanState.mediaType === 'all'
						? 'comics'
						: scanState.mediaType
					: null,
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
				// The mock's full scans end "partial": the image phase fails, so the
				// admin page shows per-phase results and every kind of issue.
				last_result: scanState.finishedAt
					? scanState.mediaType === 'all'
						? {
								status: 'partial',
								phases: { images: 'error', comics: 'done', videos: 'done' },
								message: 'images: [Errno 5] Input/output error'
							}
						: { status: 'success', phases: { [scanState.mediaType]: 'done' } }
					: null,
				// A few problems the scan ran into, once it has gone far enough.
				...(() => {
					const issues =
						count >= 50
							? [
									{
										media: 'comic',
										level: 'skipped',
										path: '/data/comics/broken.zip',
										reason: 'File is not a zip file'
									},
									{
										media: 'comic',
										level: 'skipped',
										path: '/data/comics/docs.rar',
										reason: 'No page images found'
									},
									{
										media: 'video',
										level: 'warning',
										path: '/data/videos/clip.mkv',
										reason: 'No cover/duration: ffprobe failed'
									},
									...(scanState.mediaType === 'all' && scanState.finishedAt
										? [
												{
													media: 'image',
													level: 'error',
													path: '',
													reason: 'images scan failed: [Errno 5] Input/output error'
												}
											]
										: [])
								]
							: [];
					return { issue_count: issues.length, issues };
				})()
			});
		}),
		http.post('/api/system/scan', async ({ request }) => {
			await delay(200);
			const mediaType = new URL(request.url).searchParams.get('media_type') ?? 'all';
			const status = enqueueJob('scan', { media_type: mediaType });
			return HttpResponse.json({ status, message: queueMessage(status, `Scan (${mediaType})`) });
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
		http.get('/api/tags', async () => {
			await delay(150);
			return HttpResponse.json(tagRows());
		}),
		http.post('/api/tags/kind', async ({ request }) => {
			await delay(200);
			const body = (await request.json()) as { names: string[]; kind: TagRow['kind'] };
			const names = [...new Set(body.names.map((n) => n.trim()))];
			if (!names.length || names.some((n) => !n))
				return HttpResponse.json({ msg: "Tag names can't be empty" }, { status: 400 });
			// Mirrors api/tags.py set_kind.
			for (const name of names) {
				if (body.kind === null) {
					tags.delete(name);
					for (const [n, row] of tags) if (row.canonical === name) tags.delete(n);
				} else {
					tags.set(name, { name, kind: body.kind, canonical: null, updateTime: now() });
				}
			}
			return HttpResponse.json({ tags: tagRows() });
		}),
		http.post('/api/tags/merge', async ({ request }) => {
			await delay(200);
			const body = (await request.json()) as { primary: string; aliases: string[] };
			const primary = body.primary.trim();
			const aliases = [...new Set(body.aliases.map((n) => n.trim()))].filter((n) => n !== primary);
			if (!primary || !aliases.length || aliases.some((n) => !n))
				return HttpResponse.json(
					{ msg: 'Choose at least one tag other than the primary one' },
					{ status: 400 }
				);
			// Mirrors api/tags.py merge.
			const head = tags.get(primary);
			const kind =
				head?.kind ??
				(head?.canonical ? tags.get(head.canonical)?.kind : null) ??
				aliases.map((a) => tags.get(a)?.kind).find((k) => k) ??
				null;
			tags.set(primary, { name: primary, kind, canonical: null, updateTime: now() });
			for (const name of aliases) {
				for (const row of tags.values())
					if (row.canonical === name) Object.assign(row, { canonical: primary, updateTime: now() });
				tags.set(name, { name, kind: null, canonical: primary, updateTime: now() });
			}
			return HttpResponse.json({ tags: tagRows() });
		}),
		http.post('/api/comics/move/suggest', async ({ request }) => {
			await delay(150);
			const body = (await request.json()) as { ids: number[]; name: string };
			// Mirrors mover.suggest_target, with the artist folder at its default.
			const folder = body.name
				.trim()
				.replace(/[/\\:*?"<>|]/g, '_')
				.replace(/[. ]+$/, '');
			if (!folder) return HttpResponse.json({ target: '' });
			const counts = new Map<string, number>();
			for (const c of comics.filter((x) => body.ids.includes(x.id))) {
				const parent = c.path.slice(0, c.path.lastIndexOf('/'));
				if (parent.split('/').pop() === folder) counts.set(parent, (counts.get(parent) ?? 0) + 1);
			}
			const best = [...counts].sort((a, b) => b[1] - a[1])[0];
			return HttpResponse.json({ target: best ? best[0] : `/data/comics/artist/${folder}` });
		}),
		http.post('/api/comics/move/preview', async ({ request }) => {
			await delay(400);
			const body = (await request.json()) as { ids: number[]; target: string };
			const plan = planMove(body.ids, body.target);
			return 'msg' in plan
				? HttpResponse.json(plan, { status: 400 })
				: HttpResponse.json({ target: plan.target, items: plan.items });
		}),
		http.post('/api/comics/move', async ({ request }) => {
			await delay(300);
			const body = (await request.json()) as { ids: number[]; target: string };
			const plan = planMove(body.ids, body.target);
			if ('msg' in plan) return HttpResponse.json(plan, { status: 400 });
			const ids = plan.items.filter((i) => i.status === 'move').map((i) => i.id);
			if (!ids.length) return HttpResponse.json({ msg: 'Nothing to move' }, { status: 400 });
			const params = { target: plan.target, ids: ids.join(','), count: String(ids.length) };
			const status = enqueueJob('move', params);
			const job = [jobQueue.running, ...jobQueue.queued].find(
				(j) => j?.kind === 'move' && subsumes('move', j.params, params)
			);
			return HttpResponse.json({
				jobId: job?.id ?? 0,
				status,
				message: {
					started: `Moving ${ids.length} comic(s)`,
					queued: `Moving ${ids.length} comic(s) after the running job`,
					already_queued: 'The same move is already waiting in the queue'
				}[status]
			});
		}),
		// Registered before /api/comics/:id so the literal path wins.
		http.get('/api/comics/stats', async ({ request }) => {
			await delay(500);
			const count = Number(new URL(request.url).searchParams.get('months') ?? 12);
			if (!Number.isInteger(count) || count < 1 || count > 60) {
				return HttpResponse.json({ msg: 'Invalid months' }, { status: 400 });
			}
			const live = comics.filter((c) => !c.archived && !c.missing);
			const now = new Date();
			// Activity is random but steady per page load: the log "started" 30
			// months ago, so longer ranges show full history.
			const months = [...Array(count).keys()].reverse().map((back) => {
				const d = new Date(now.getFullYear(), now.getMonth() - back, 1);
				const month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
				const stat = mockMonthStats.get(month) ?? {
					added: faker.number.int({ min: 0, max: 40 }),
					read: faker.number.int({ min: 0, max: 25 }),
					readDays: 0,
					deleted: faker.number.int({ min: 0, max: 8 }),
					deletedSize: 0
				};
				stat.readDays = Math.max(stat.readDays, stat.read + faker.number.int({ min: 0, max: 15 }));
				stat.deletedSize ||= stat.deleted * faker.number.int({ min: 20, max: 300 }) * 1024 * 1024;
				mockMonthStats.set(month, stat);
				return { month, ...stat };
			});
			const sum = (key: 'added' | 'readDays' | 'deleted' | 'deletedSize') =>
				months.reduce((n, m) => n + m[key], 0);
			const since = new Date(now.getFullYear(), now.getMonth() - 29, 3);
			return HttpResponse.json({
				library: {
					total: live.length,
					totalSize: live.reduce((n, c) => n + c.size, 0),
					favorited: live.filter((c) => c.favorited).length,
					started: live.filter((c) => c.lastViewedTime).length,
					finished: live.filter((c) => c.page > 0 && (c.lastViewedPosition ?? 0) >= c.page).length,
					archived: comics.filter((c) => c.archived).length
				},
				since: since.toISOString(),
				total: {
					added: sum('added'),
					read: Math.min(
						live.length,
						months.reduce((n, m) => n + m.read, 0)
					),
					readDays: sum('readDays'),
					deleted: sum('deleted'),
					deletedSize: sum('deletedSize')
				},
				months,
				topRead: live.slice(0, 10).map((c, i) => ({ id: c.id, name: c.name, readDays: 20 - i * 2 }))
			});
		}),
		// Registered before /api/comics/:id so the literal path wins.
		http.get('/api/comics/duplicates', async () => {
			await delay(800);
			const buckets = new Map<string, typeof comics>();
			for (const c of comics) {
				if (c.archived || c.missing) continue;
				const key = duplicateKey(c.name);
				if (!key) continue;
				buckets.set(key, [...(buckets.get(key) ?? []), c]);
			}
			// Stand-in for the fuzzy pass: a title that extends another title is
			// merged into it as a similar (not exact) group.
			const merged: { exact: boolean; items: typeof comics }[] = [];
			const entries = [...buckets.entries()].sort(([a], [b]) => a.length - b.length);
			const keys = entries.map(([k]) => k);
			const owner = new Map<string, (typeof merged)[number]>();
			for (const [key, items] of entries) {
				const base = keys.find((k) => k !== key && k.length >= 6 && key.startsWith(k));
				const target = base ? owner.get(base) : undefined;
				if (target) {
					target.items = [...target.items, ...items];
					target.exact = false;
					owner.set(key, target);
				} else {
					const group = { exact: true, items };
					merged.push(group);
					owner.set(key, group);
				}
			}
			const groups = merged
				.filter(({ items }) => items.length > 1)
				.map(({ exact, items }) => {
					// Same preference as the backend: favorited, most pages, largest.
					const rank = (c: (typeof items)[number]) =>
						Number(c.favorited) * 1e12 + c.page * 1e8 + c.size;
					const keep = items.reduce((best, c) => (rank(c) > rank(best) ? c : best));
					return { exact, keepId: keep.id, items };
				});
			return HttpResponse.json({ groups });
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
				name: `page_${String(i + 1).padStart(3, '0')}.jpg`,
				size: faker.number.int({ min: 40_000, max: 1_500_000 })
			}));
			return HttpResponse.json({ pageDetails });
		}),
		http.get('/api/comics/:id/pages/:page/info', async ({ params }) => {
			await delay(150);
			const comic = findComic(params.id);
			const page = Number(params.page);
			if (!comic || page < 1 || page > comic.page)
				return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			return HttpResponse.json(mockPageInfo(comic.id, page));
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
			return HttpResponse.json({ detail: 'OK' });
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
		// Mirrors api/home.py: up to 12 per type and section, archived and
		// missing items left out. Mock videos aren't implemented, so the video
		// lists stay empty.
		http.get('/api/home', async () => {
			await delay(600);
			const n = 12;
			type Item = (typeof comics)[number];
			const visible = (list: Item[]) => list.filter((e) => !e.archived && !e.missing);
			const desc = (key: (e: Item) => string | null | undefined) => (a: Item, b: Item) =>
				(key(b) ?? '').localeCompare(key(a) ?? '');
			const inProgress = (e: Item) =>
				!!e.lastViewedTime &&
				(e.lastViewedPosition ?? 0) > 0 &&
				(e.lastViewedPosition ?? 0) < e.page;
			const newest = (list: Item[]) =>
				[...visible(list)].sort(desc((e) => e.updateTime)).slice(0, n);
			return HttpResponse.json({
				continueReading: {
					comics: visible(comics)
						.filter(inProgress)
						.sort(desc((e) => e.lastViewedTime))
						.slice(0, n),
					videos: [],
					images: visible(images)
						.filter(inProgress)
						.sort(desc((e) => e.lastViewedTime))
						.slice(0, n)
				},
				recent: { comics: newest(comics), videos: [], images: newest(images) },
				favorites: { comics: newest(comics.filter((e) => e.favorited)), videos: [], images: [] },
				random: {
					comics: faker.helpers.arrayElements(visible(comics), n),
					videos: [],
					images: faker.helpers.arrayElements(visible(images), n)
				}
			});
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
				name: `image_${String(i + 1).padStart(3, '0')}.jpg`,
				size: faker.number.int({ min: 40_000, max: 1_500_000 })
			}));
			return HttpResponse.json({ pageDetails });
		}),
		http.get('/api/images/:id/pages/:page/info', async ({ params }) => {
			await delay(150);
			const image = findImage(params.id);
			const page = Number(params.page);
			if (!image || page < 1 || page > image.page)
				return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			return HttpResponse.json(mockPageInfo(image.id, page));
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
		http.post('/api/images/:id/pages/:page/like', async ({ params }) => {
			await delay(200);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const page = Number(params.page);
			if (page < 1 || page > image.page) {
				return HttpResponse.json({ msg: 'Page not found' }, { status: 404 });
			}
			return HttpResponse.json({ detail: 'OK' });
		}),
		http.post('/api/images/:id/rename', async ({ params, request }) => {
			await delay(400);
			const image = findImage(params.id);
			if (!image) return HttpResponse.json({ msg: 'Not found' }, { status: 404 });
			const body = (await request.json()) as { name: string };
			if (body.name === image.name) {
				return HttpResponse.json({ msg: 'Name is same' }, { status: 400 });
			}
			// Mirror the backend: the folder is renamed in place.
			image.path = image.path.slice(0, image.path.length - image.name.length) + body.name;
			image.name = body.name;
			return HttpResponse.json({ name: body.name });
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
