import { adapterFor, type MediaAdapter } from '$lib/mediaAdapters';
import type { MediaFile } from '$lib/model.svelte';

async function loadAll(adapter: MediaAdapter): Promise<MediaFile[]> {
	const result = await adapter.list();
	if (result.error !== undefined) {
		throw new Error(result.error);
	}
	return result.data;
}

// Session-scoped cache of the full per-media-type list. Home / folder / tag and
// global search all consume the same full list, so we fetch each type at most
// once and share the promise across views. A page reload clears this (the module
// re-initializes), which is the intended "give me fresh data" trigger; within a
// session only an explicit refresh re-fetches (see refreshMediaFiles).
const cache = new Map<string, Promise<MediaFile[]>>();

export function getMediaFiles(mediaType: string): Promise<MediaFile[]> | undefined {
	const adapter = adapterFor(mediaType);
	if (!adapter) {
		return undefined;
	}
	let pending = cache.get(mediaType);
	if (!pending) {
		// Don't poison the cache with a rejected promise: drop it on failure so the
		// next navigation (or refresh) retries instead of replaying the error.
		pending = loadAll(adapter).catch((err) => {
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
