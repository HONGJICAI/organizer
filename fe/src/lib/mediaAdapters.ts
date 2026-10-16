import { ComicpageService, ComicsService, ImagesService, VideosService } from '$lib/client';
import type { ComicEntity, ImageEntity, VideoEntity } from '$lib/client';
import { Comic, Image, MediaType, Video, type MediaFile } from '$lib/model.svelte';

// Everything that differs per media type, in one table. Components call
// `adapters[file.type].op(...)` instead of picking an API service themselves:
// picking by hand is how image albums and videos ended up calling comic
// endpoints with their own ids (favorite, rename, set cover, like, details).
//
// An optional operation is absent when the type doesn't support it; UI shows
// the matching control only when the operation exists, so "can do X" and "how
// to do X" can't drift apart. Typing the table as Record<MediaType, ...> makes a
// new media type fail to compile until it has an adapter.

// A request's outcome with the API error normalized to a message.
export type Outcome<T> = { data: T; error?: undefined } | { data?: undefined; error: string };

type Entity = ComicEntity | VideoEntity | ImageEntity;
export type PageDetail = { name: string; size: number };
export type PageInfo = { width: number; height: number; format: string };
type PageDetails = { pageDetails: PageDetail[] };

export interface MediaAdapter {
	/** Noun for confirmations, e.g. "Confirm delete comic". */
	label: string;
	/** Text tags are split from: the file name for comics, the path otherwise. */
	tagSource(file: MediaFile): string;
	/** API path of a 1-based page (0 is the cover); absent for videos. */
	pagePath?(id: number, page: number): string;

	list(): Promise<Outcome<MediaFile[]>>;
	get(id: number): Promise<Outcome<MediaFile>>;
	/**
	 * Delete from disk. Archivable types keep the record (as archived) unless
	 * `permanent`; the rest always drop it.
	 */
	remove(id: number, permanent: boolean): Promise<Outcome<void>>;
	archivable: boolean;

	rename?(id: number, name: string): Promise<Outcome<void>>;
	refresh?(id: number): Promise<Outcome<Entity>>;
	favor?(id: number, favorited: boolean): Promise<Outcome<boolean>>;
	detail?(id: number): Promise<Outcome<PageDetails>>;
	// Original width/height/format of one 1-based page.
	pageInfo?(id: number, page: number): Promise<Outcome<PageInfo>>;
	deletePage?(id: number, page: number): Promise<Outcome<Entity>>;
	likePage?(id: number, page: number): Promise<Outcome<void>>;
	setCover?(id: number, page: number): Promise<Outcome<void>>;
	updateProgress?(id: number, position: number): Promise<Outcome<void>>;
	/** Package the item as a new comic; resolves to the comic's name. */
	convertToComic?(id: number): Promise<Outcome<string>>;
}

export function errorMessage(error: unknown): string {
	if (error && typeof error === 'object' && 'msg' in error && typeof error.msg === 'string') {
		return error.msg;
	}
	return 'Request failed';
}

type SdkResult<T> = Promise<{ data?: T; error?: unknown }>;

async function call<T, R = T>(request: SdkResult<T>, map?: (data: T) => R): Promise<Outcome<R>> {
	const { data, error } = await request;
	if (error !== undefined || data === undefined) return { error: errorMessage(error) };
	return { data: map ? map(data) : (data as unknown as R) };
}

// For endpoints whose success body the UI doesn't use.
async function callVoid(request: SdkResult<unknown>): Promise<Outcome<void>> {
	const { error } = await request;
	return error !== undefined ? { error: errorMessage(error) } : { data: undefined };
}

export const comicAdapter = {
	label: 'comic',
	tagSource: (file) => file.name,
	pagePath: (id, page) => `/api/comics/${id}/pages/${page}`,
	list: () => call(ComicsService.comicGetAll(), (es) => es.map((e) => new Comic(e))),
	get: (id) => call(ComicsService.comicGet({ path: { id } }), (e) => new Comic(e)),
	archivable: true,
	remove: (id, permanent) =>
		callVoid(ComicsService.comicDelete({ path: { id }, query: { permanent } })),
	rename: (id, name) => callVoid(ComicsService.comicRename({ path: { id }, body: { name } })),
	refresh: (id) => call(ComicsService.comicRefresh({ path: { id } })),
	favor: (id, favorited) =>
		call(
			favorited
				? ComicsService.comicFavor({ path: { id } })
				: ComicsService.comicUnfavor({ path: { id } }),
			(r) => r.favorited
		),
	detail: (id) => call(ComicsService.comicDetail({ path: { id } })),
	pageInfo: (id, page) => call(ComicpageService.comicPageInfo({ path: { id, page } })),
	likePage: (id, page) => callVoid(ComicpageService.comicPageLike({ path: { id, page } })),
	setCover: (id, page) => callVoid(ComicpageService.comicPageSetCover({ path: { id, page } })),
	updateProgress: (id, position) =>
		callVoid(ComicpageService.comicPageUpdateProgress({ path: { id }, body: { position } }))
} satisfies MediaAdapter;

export const videoAdapter = {
	label: 'video',
	tagSource: (file) => file.path,
	list: () => call(VideosService.videoGetAll(), (es) => es.map((e) => new Video(e))),
	get: (id) => call(VideosService.videoGet({ path: { id } }), (e) => new Video(e)),
	archivable: true,
	remove: (id, permanent) =>
		callVoid(VideosService.videoDelete({ path: { id }, query: { permanent } }))
} satisfies MediaAdapter;

export const imageAdapter = {
	label: 'image folder',
	tagSource: (file) => file.path,
	pagePath: (id, page) => `/api/images/${id}/pages/${page}`,
	list: () => call(ImagesService.imageGetAll(), (es) => es.map((e) => new Image(e))),
	get: (id) => call(ImagesService.imageGet({ path: { id } }), (e) => new Image(e)),
	// Albums have no database record to archive: deleting always removes it.
	archivable: false,
	remove: (id) => callVoid(ImagesService.imageDelete({ path: { id } })),
	rename: (id, name) => callVoid(ImagesService.imageRename({ path: { id }, body: { name } })),
	refresh: (id) => call(ImagesService.imageRefresh({ path: { id } })),
	detail: (id) => call(ImagesService.imageDetail({ path: { id } })),
	pageInfo: (id, page) => call(ImagesService.imagePageInfo({ path: { id, page } })),
	deletePage: (id, page) => call(ImagesService.imageDeletePage({ path: { id, page } })),
	likePage: (id, page) => callVoid(ImagesService.imageLike({ path: { id, page } })),
	updateProgress: (id, position) =>
		callVoid(ImagesService.imageUpdateProgress({ path: { id }, body: { position } })),
	convertToComic: (id) => call(ImagesService.imageConvert({ path: { id } }), (c) => c.name)
} satisfies MediaAdapter;

export const adapters: Record<MediaType, MediaAdapter> = {
	[MediaType.Comic]: comicAdapter,
	[MediaType.Video]: videoAdapter,
	[MediaType.Image]: imageAdapter
};

/** The adapter for a route's `mediaType` param, or undefined for an unknown one. */
export function adapterFor(mediaType: string): MediaAdapter | undefined {
	return (adapters as Record<string, MediaAdapter>)[mediaType];
}
