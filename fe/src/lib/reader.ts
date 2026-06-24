import { config, PageWidthMode, ViewMode } from '$lib/config.svelte';
import { authState } from '$lib/auth.svelte';
import { MediaType } from '$lib/model.svelte';

// Server-side page width cap, keep in sync with the backend's `width` query param.
export const MAX_PAGE_WIDTH = 4096;

// The requested render width for a comic/image page, or null to let the backend
// serve the original. Reads the user's page-width preference from config.
export function pageWidth(): number | null {
	switch (config.pageWidthMode) {
		case PageWidthMode.Device:
			return Math.min(
				MAX_PAGE_WIDTH,
				Math.round(window.innerWidth * (window.devicePixelRatio || 1))
			);
		case PageWidthMode.Custom:
			return config.pageWidthCustom > 0
				? Math.min(MAX_PAGE_WIDTH, Math.round(config.pageWidthCustom))
				: null;
		default:
			return null;
	}
}

// Build the media URL for a single comic/image page. These are loaded by an
// <img> element, which cannot send an Authorization header, so auth rides on
// the `?token=` query param (backend require_media_auth) instead of the SDK.
// `widthOverride` forces a specific server-side render width (e.g. small
// thumbnails for the overview grid), bypassing the user's page-width setting.
export function pageApiUrl(
	mediaType: MediaType,
	id: number,
	pageNum: number,
	widthOverride?: number
): string {
	const base =
		mediaType === MediaType.Image
			? `${config.apiServer}/api/images/${id}/pages/${pageNum}`
			: `${config.apiServer}/api/comics/${id}/pages/${pageNum}`;
	const params = new URLSearchParams();
	if (authState.token) params.set('token', authState.token);
	const width = widthOverride ?? pageWidth();
	if (width) params.set('width', String(width));
	const qs = params.toString();
	return qs ? `${base}?${qs}` : base;
}

// Compute the target page for a single navigation step in the paged reader.
// Pages are 1-based (valid range 1..maxPage). `dir` is +1 (next) or -1 (prev).
// When `loop` is true the page wraps around both ends (used by the keyboard
// arrows and the looping PaginationNav); otherwise it clamps at the boundaries
// and returns the *same* page when there is nowhere to go — callers rely on
// that no-op signal to avoid kicking off a navigation that never changes the
// page (which would otherwise leave the reader's `loading` flag stuck, since
// it is only cleared by the <img> load/error handlers).
export function stepPage(page: number, maxPage: number, dir: 1 | -1, loop = false): number {
	if (maxPage <= 0) return page;
	if (loop) {
		return ((page - 1 + dir + maxPage) % maxPage) + 1;
	}
	return Math.min(maxPage, Math.max(1, page + dir));
}

// CSS class for the active view mode, shared by the comic/image readers and the
// video player so they size their media identically.
export function viewModeClass(mode: ViewMode): string {
	switch (mode) {
		case ViewMode.Width:
			return 'fit-to-width';
		case ViewMode.Height:
			return 'fit-to-height';
		case ViewMode.Scroll:
			return 'fit-to-scroll';
		case ViewMode.Contain:
		default:
			return 'fit-to-contain';
	}
}
