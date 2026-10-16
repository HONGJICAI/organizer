import type { PageDetail } from '$lib/mediaAdapters';

export const viewerState = $state({
	active: false,
	title: '',
	page: 0,
	maxPage: 0,
	// Whether the full-screen page-thumbnail overview is open. Toggled from the
	// header page counter; rendered by the reader (which holds the file).
	overviewOpen: false,
	// Private reading: the open file's progress isn't saved (no "viewed" mark,
	// no read in stats). Set by the reader on open (`?private=1`, used by the
	// duplicate finder); the header chip turns it off to start saving.
	privateReading: false,
	// Per-page file name and size of the open comic/album, for the header's
	// page info. Empty until loaded, and for media without pages.
	pageDetails: [] as PageDetail[],
	// eslint-disable-next-line @typescript-eslint/no-empty-function
	onClose: () => {},
	// Reverse channel from the chrome/overview to the active reader: jump to a
	// 1-based page. Each reader registers its own implementation on mount. The
	// explicit void return type lets a reader register an async handler.
	gotoPage: (page: number): void => {
		void page;
	}
});
