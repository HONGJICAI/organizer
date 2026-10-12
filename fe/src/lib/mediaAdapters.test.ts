import { describe, it, expect, vi, beforeEach } from 'vitest';

// Every SDK method resolves to a successful empty response unless a test says
// otherwise; the assertions are about which endpoint each adapter calls.
const sdk = vi.hoisted(() => {
	const ok = () => Promise.resolve({ data: {}, error: undefined });
	const service = (...names: string[]) =>
		Object.fromEntries(names.map((n) => [n, vi.fn(ok)])) as Record<
			string,
			ReturnType<typeof vi.fn>
		>;
	return {
		ComicsService: service(
			'comicGetAll',
			'comicGet',
			'comicDelete',
			'comicRename',
			'comicRefresh',
			'comicFavor',
			'comicUnfavor',
			'comicDetail'
		),
		ComicpageService: service('comicPageLike', 'comicPageSetCover', 'comicPageUpdateProgress'),
		VideosService: service('videoGetAll', 'videoGet', 'videoDelete'),
		ImagesService: service(
			'imageGetAll',
			'imageGet',
			'imageDelete',
			'imageRename',
			'imageRefresh',
			'imageDetail',
			'imageDeletePage',
			'imageLike',
			'imageUpdateProgress',
			'imageConvert'
		)
	};
});
vi.mock('$lib/client/sdk.gen.js', () => sdk);

import {
	adapterFor,
	adapters,
	comicAdapter as comic,
	errorMessage,
	imageAdapter as image,
	videoAdapter as video,
	type MediaAdapter
} from './mediaAdapters';
import { Comic, Image, MediaType, Video } from './model.svelte';

const allMocks = () =>
	Object.values(sdk).flatMap((service) => Object.values(service)) as ReturnType<typeof vi.fn>[];

beforeEach(() => {
	for (const fn of allMocks()) fn.mockClear();
});

const entity = { id: 7, name: 'n', path: '/p/n', size: 0, updateTime: '2026-01-01T00:00:00' };

// The optional operations each type must (and must only) support. Spelled out
// so adding or dropping an operation is a deliberate, reviewed change.
const supported: Record<MediaType, (keyof MediaAdapter)[]> = {
	[MediaType.Comic]: [
		'pagePath',
		'rename',
		'refresh',
		'favor',
		'detail',
		'likePage',
		'setCover',
		'updateProgress'
	],
	[MediaType.Video]: [],
	[MediaType.Image]: [
		'pagePath',
		'rename',
		'refresh',
		'detail',
		'deletePage',
		'likePage',
		'updateProgress',
		'convertToComic'
	]
};
const optional: (keyof MediaAdapter)[] = [
	'pagePath',
	'rename',
	'refresh',
	'favor',
	'detail',
	'deletePage',
	'likePage',
	'setCover',
	'updateProgress',
	'convertToComic'
];

describe('capabilities', () => {
	for (const type of Object.values(MediaType)) {
		it(`${type} supports exactly its operations`, () => {
			const present = optional.filter((op) => adapters[type][op] !== undefined);
			expect(present).toEqual(supported[type]);
		});
	}

	it('only comics and videos keep an archived record on delete', () => {
		expect(adapters[MediaType.Comic].archivable).toBe(true);
		expect(adapters[MediaType.Video].archivable).toBe(true);
		expect(adapters[MediaType.Image].archivable).toBe(false);
	});
});

describe('each type calls its own endpoints', () => {
	it('likePage', async () => {
		await comic.likePage(7, 2);
		expect(sdk.ComicpageService.comicPageLike).toHaveBeenCalledWith({ path: { id: 7, page: 2 } });
		await image.likePage(7, 2);
		expect(sdk.ImagesService.imageLike).toHaveBeenCalledWith({ path: { id: 7, page: 2 } });
		expect(sdk.ComicpageService.comicPageLike).toHaveBeenCalledTimes(1);
	});

	it('rename', async () => {
		await image.rename(7, 'x');
		expect(sdk.ImagesService.imageRename).toHaveBeenCalledWith({
			path: { id: 7 },
			body: { name: 'x' }
		});
		expect(sdk.ComicsService.comicRename).not.toHaveBeenCalled();
	});

	it('detail and refresh', async () => {
		await image.detail(7);
		await image.refresh(7);
		expect(sdk.ImagesService.imageDetail).toHaveBeenCalledOnce();
		expect(sdk.ImagesService.imageRefresh).toHaveBeenCalledOnce();
		expect(sdk.ComicsService.comicDetail).not.toHaveBeenCalled();
		expect(sdk.ComicsService.comicRefresh).not.toHaveBeenCalled();
	});

	it('updateProgress', async () => {
		await comic.updateProgress(7, 3);
		await image.updateProgress(8, 4);
		expect(sdk.ComicpageService.comicPageUpdateProgress).toHaveBeenCalledWith({
			path: { id: 7 },
			body: { position: 3 }
		});
		expect(sdk.ImagesService.imageUpdateProgress).toHaveBeenCalledWith({
			path: { id: 8 },
			body: { position: 4 }
		});
	});

	it('remove passes permanent only where records can be archived', async () => {
		await comic.remove(7, false);
		await video.remove(7, true);
		// Through the table, as components call it: albums ignore `permanent`.
		await adapters[MediaType.Image].remove(7, false);
		expect(sdk.ComicsService.comicDelete).toHaveBeenCalledWith({
			path: { id: 7 },
			query: { permanent: false }
		});
		expect(sdk.VideosService.videoDelete).toHaveBeenCalledWith({
			path: { id: 7 },
			query: { permanent: true }
		});
		expect(sdk.ImagesService.imageDelete).toHaveBeenCalledWith({ path: { id: 7 } });
	});

	it('page paths', () => {
		expect(comic.pagePath(7, 2)).toBe('/api/comics/7/pages/2');
		expect(image.pagePath(7, 2)).toBe('/api/images/7/pages/2');
	});
});

describe('results', () => {
	it('favor picks favor/unfavor and returns the new state', async () => {
		sdk.ComicsService.comicFavor.mockResolvedValueOnce({ data: { favorited: true } });
		expect(await comic.favor(7, true)).toEqual({ data: true });
		sdk.ComicsService.comicUnfavor.mockResolvedValueOnce({ data: { favorited: false } });
		expect(await comic.favor(7, false)).toEqual({ data: false });
	});

	it('list and get build model instances', async () => {
		sdk.ComicsService.comicGetAll.mockResolvedValueOnce({ data: [entity] });
		sdk.VideosService.videoGet.mockResolvedValueOnce({ data: entity });
		sdk.ImagesService.imageGet.mockResolvedValueOnce({ data: entity });
		const comics = await comic.list();
		expect(comics.data?.[0]).toBeInstanceOf(Comic);
		expect((await video.get(7)).data).toBeInstanceOf(Video);
		expect((await image.get(7)).data).toBeInstanceOf(Image);
	});

	it('convertToComic resolves to the new comic name', async () => {
		sdk.ImagesService.imageConvert.mockResolvedValueOnce({ data: { ...entity, name: 'a.zip' } });
		expect(await image.convertToComic(7)).toEqual({ data: 'a.zip' });
	});

	it('normalizes API errors to their message', async () => {
		sdk.ImagesService.imageRename.mockResolvedValueOnce({ error: { msg: 'Name is same' } });
		expect(await image.rename(7, 'x')).toEqual({ error: 'Name is same' });
		sdk.ComicsService.comicGet.mockResolvedValueOnce({ error: { detail: [] } });
		expect(await comic.get(7)).toEqual({ error: 'Request failed' });
	});

	it('void operations succeed without a body', async () => {
		sdk.ImagesService.imageLike.mockResolvedValueOnce({ data: undefined });
		expect(await image.likePage(7, 1)).toEqual({ data: undefined });
	});
});

describe('helpers', () => {
	it('tagSource: comics by name, others by path', () => {
		const c = new Comic({ ...entity, page: 1 });
		const v = new Video({ ...entity, durationInSecond: 0 });
		const i = new Image({ ...entity, page: 1 });
		expect(adapters[c.type].tagSource(c)).toBe('n');
		expect(adapters[v.type].tagSource(v)).toBe('/p/n');
		expect(adapters[i.type].tagSource(i)).toBe('/p/n');
	});

	it('adapterFor rejects unknown route params', () => {
		expect(adapterFor('comic')).toBe(adapters[MediaType.Comic]);
		expect(adapterFor('bogus')).toBeUndefined();
	});

	it('errorMessage falls back for non-message errors', () => {
		expect(errorMessage({ msg: 'x' })).toBe('x');
		expect(errorMessage(new Error('boom'))).toBe('Request failed');
		expect(errorMessage(undefined)).toBe('Request failed');
	});
});
