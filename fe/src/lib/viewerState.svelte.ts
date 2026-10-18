import type { PageDetail, PageInfo } from '$lib/mediaAdapters';

const PRIVATE_KEY = 'organizer.privateReading';

// Session-wide private reading lives in sessionStorage, so it survives reloads
// but ends with the tab rather than being forgotten on forever.
function loadPrivateSession(): boolean {
	try {
		return sessionStorage.getItem(PRIVATE_KEY) === '1';
	} catch {
		return false;
	}
}

export const viewerState = $state({
	active: false,
	title: '',
	page: 0,
	maxPage: 0,
	// Whether the full-screen page-thumbnail overview is open. Toggled from the
	// header page counter; rendered by the reader (which holds the file).
	overviewOpen: false,
	// Private reading: the open file's progress isn't saved (no "viewed" mark,
	// no read in stats). Set by the reader on open from privateSession or
	// `?private=1` (used by the duplicate finder, for that one file only).
	privateReading: loadPrivateSession(),
	// Session-wide private reading: every file opened while it's on starts
	// private. Toggled from the header with setPrivateReading().
	privateSession: loadPrivateSession(),
	// Per-page file name and size of the open comic/album, for the header's
	// page info. Empty until loaded, and for media without pages.
	pageDetails: [] as PageDetail[],
	// Original width/height/format by 1-based page, fetched one page at a time
	// while the page info is shown. null: the page isn't a readable image.
	pageInfos: {} as Record<number, PageInfo | null>,
	// eslint-disable-next-line @typescript-eslint/no-empty-function
	onClose: () => {},
	// Reverse channel from the chrome/overview to the active reader: jump to a
	// 1-based page. Each reader registers its own implementation on mount. The
	// explicit void return type lets a reader register an async handler.
	gotoPage: (page: number): void => {
		void page;
	}
});

// The header toggle: switches the open file and the session together, so
// turning it on before opening a file keeps even the first page unsaved.
export function setPrivateReading(on: boolean) {
	viewerState.privateReading = on;
	viewerState.privateSession = on;
	try {
		if (on) sessionStorage.setItem(PRIVATE_KEY, '1');
		else sessionStorage.removeItem(PRIVATE_KEY);
	} catch {
		// Storage unavailable: the setting still holds until reload.
	}
}
