import { ComicpageService, ImagesService } from '$lib/client';
import { MediaType, type MediaFile } from '$lib/model.svelte';

// Reports comic/image reading progress to the backend. Calls are deduped (a
// repeated position is skipped) and debounced by the caller via schedule(), so
// flipping through pages only sends the position the reader settles on. The
// position is also mirrored onto the in-memory file so cached list views (the
// viewed badge, Recent, sort-by-viewed) stay consistent without a refetch.
// Fire and forget; videos are ignored.
export function createProgressReporter(file: MediaFile, debounceMs = 1000) {
	let reported = 0;
	let pending = 0;
	let timer: ReturnType<typeof setTimeout> | null = null;

	function send(position: number) {
		if (position === reported || position < 1) return;
		if (file.type !== MediaType.Comic && file.type !== MediaType.Image) return;
		reported = position;
		const opts = { path: { id: file.id }, body: { position } };
		if (file.type === MediaType.Comic) {
			ComicpageService.comicPageUpdateProgress(opts);
		} else {
			ImagesService.imageUpdateProgress(opts);
		}
		const now = new Date();
		file.lastViewed = position;
		file.lastViewedTime = now.toISOString();
		file.lastViewedDate = now;
	}

	return {
		// Queue a report for `position`, replacing any pending one.
		schedule(position: number) {
			pending = position;
			if (timer) clearTimeout(timer);
			timer = setTimeout(() => send(position), debounceMs);
		},
		// Send any pending report immediately, e.g. when the viewer unmounts
		// within the debounce window.
		flush() {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
			send(pending);
		}
	};
}
