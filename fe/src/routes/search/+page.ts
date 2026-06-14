import { getMediaFiles } from '$lib/mediaStore';
import type { MediaFile } from '$lib/model.svelte';

// Global search consumes the same full per-type lists as the list pages, so it
// shares mediaStore's cache (no extra fetch when arriving from a list page). A
// failure in one type must not blank the others, so each promise resolves to []
// on error.
function safeLoad(mediaType: string): Promise<MediaFile[]> {
	return (getMediaFiles(mediaType) ?? Promise.resolve([])).catch(() => []);
}

export function load() {
	return {
		comics: safeLoad('comic'),
		videos: safeLoad('video'),
		images: safeLoad('image')
	};
}
