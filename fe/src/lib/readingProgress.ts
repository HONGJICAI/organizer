import { adapters } from '$lib/mediaAdapters';
import type { MediaFile } from '$lib/model.svelte';

// Reports comic/image reading progress to the backend. Calls are deduped (a
// repeated position is skipped) and debounced by the caller via schedule(), so
// flipping through pages only sends the position the reader settles on. The
// position is also mirrored onto the in-memory file so cached list views (the
// viewed badge, Recent, sort-by-viewed) stay consistent without a refetch.
// Fire and forget; types without progress tracking (videos) are ignored.
export function createProgressReporter(file: MediaFile, debounceMs = 1000) {
	let reported = 0;
	let pending = 0;
	let timer: ReturnType<typeof setTimeout> | null = null;

	function send(position: number) {
		const update = adapters[file.type].updateProgress;
		if (position === reported || position < 1 || !update) return;
		reported = position;
		update(file.id, position);
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
