export const viewerState = $state({
	active: false,
	title: '',
	page: 0,
	maxPage: 0,
	// Whether the full-screen page-thumbnail overview is open. Toggled from the
	// header page counter; rendered by the reader (which holds the file).
	overviewOpen: false,
	// eslint-disable-next-line @typescript-eslint/no-empty-function
	onClose: () => {},
	// Reverse channel from the chrome/overview to the active reader: jump to a
	// 1-based page. Each reader registers its own implementation on mount.
	gotoPage: (page: number) => void page
});
