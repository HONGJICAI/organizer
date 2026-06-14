import { ComicsService, ImagesService, VideosService } from '$lib/client/sdk.gen.js';
import { Comic, Image, Video, type MediaFile } from '$lib/model.svelte';

type Loader = () => Promise<MediaFile[]>;

const loaders: Record<string, Loader> = {
	comic: async () => {
		const { data, error } = await ComicsService.comicGetAll();
		if (error) {
			throw error;
		}
		return data.map((e) => new Comic(e));
	},
	video: async () => {
		const { data, error } = await VideosService.videoGetAll();
		if (error) {
			throw error;
		}
		return data.map((e) => new Video(e));
	},
	image: async () => {
		const { data, error } = await ImagesService.imageGetAll();
		if (error) {
			throw error;
		}
		return data.map((e) => new Image(e));
	}
};

// Session-scoped cache of the full per-media-type list. Home / folder / tag and
// global search all consume the same full list, so we fetch each type at most
// once and share the promise across views. A page reload clears this (the module
// re-initializes), which is the intended "give me fresh data" trigger; within a
// session only an explicit refresh re-fetches (see refreshMediaFiles).
const cache = new Map<string, Promise<MediaFile[]>>();

export function getMediaFiles(mediaType: string): Promise<MediaFile[]> | undefined {
	const loader = loaders[mediaType];
	if (!loader) {
		return undefined;
	}
	let pending = cache.get(mediaType);
	if (!pending) {
		// Don't poison the cache with a rejected promise: drop it on failure so the
		// next navigation (or refresh) retries instead of replaying the error.
		pending = loader().catch((err) => {
			cache.delete(mediaType);
			throw err;
		});
		cache.set(mediaType, pending);
	}
	return pending;
}

export function refreshMediaFiles(mediaType?: string) {
	if (mediaType) {
		cache.delete(mediaType);
	} else {
		cache.clear();
	}
}
