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
export function pageApiUrl(mediaType: MediaType, id: number, pageNum: number): string {
	const base =
		mediaType === MediaType.Image
			? `${config.apiServer}/api/images/${id}/pages/${pageNum}`
			: `${config.apiServer}/api/comics/${id}/pages/${pageNum}`;
	const params = new URLSearchParams();
	if (authState.token) params.set('token', authState.token);
	const width = pageWidth();
	if (width) params.set('width', String(width));
	const qs = params.toString();
	return qs ? `${base}?${qs}` : base;
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
