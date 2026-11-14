import { config } from '$lib/config.svelte';

// Thumbnail size levels of the page overview (the reader's page grid), S to XL.
// Desktop lays tiles out by minimum width; phones by a fixed column count.
// `thumb` is the CSS width a tile is drawn at on desktop, used to pick the
// server-side render width; `batch` is how many tiles one overview screen holds,
// fewer as they grow so a screen never fires a lot of large image requests.
export interface OverviewSize {
	label: string;
	minWidthRem: number;
	thumb: number;
	mobileColumns: number;
	batch: number;
}

export const OVERVIEW_SIZES: readonly OverviewSize[] = [
	{ label: 'S', minWidthRem: 7, thumb: 200, mobileColumns: 4, batch: 60 },
	{ label: 'M', minWidthRem: 11, thumb: 320, mobileColumns: 3, batch: 40 },
	{ label: 'L', minWidthRem: 16, thumb: 480, mobileColumns: 2, batch: 24 },
	{ label: 'XL', minWidthRem: 24, thumb: 720, mobileColumns: 1, batch: 12 }
];

export const DEFAULT_OVERVIEW_SIZE = 0;

export function clampLevel(level: number): number {
	if (!Number.isFinite(level)) return DEFAULT_OVERVIEW_SIZE;
	return Math.min(OVERVIEW_SIZES.length - 1, Math.max(0, Math.round(level)));
}

export function isLevel(value: unknown): value is number {
	return Number.isInteger(value) && clampLevel(value as number) === value;
}

// Render widths the overview ever asks the server for. Requests snap up to one
// of these so the browser cache keeps hitting across levels, screens and pixel
// ratios instead of every tile width producing a new URL.
const THUMB_WIDTHS = [200, 320, 480, 720, 960, 1440, 2048];

// Server-side width for a tile drawn `cssWidth` px wide. The pixel ratio is
// capped at 2: past that the extra bytes aren't visible in a thumbnail.
export function thumbRequestWidth(cssWidth: number, devicePixelRatio = 1): number {
	const want = cssWidth * Math.min(Math.max(devicePixelRatio, 1), 2);
	return THUMB_WIDTHS.find((w) => w >= want) ?? THUMB_WIDTHS[THUMB_WIDTHS.length - 1];
}

// 1-based batch holding a 1-based page.
export function batchOf(page: number, batchSize: number): number {
	return Math.floor((Math.max(page, 1) - 1) / batchSize) + 1;
}

// The size set in the overview lasts for the tab's session; the default for new
// sessions is a setting (config.overviewSize, saved with the other prefs).
const SESSION_KEY = 'organizer.overviewSize';

export function sessionOverviewSize(): number | null {
	try {
		const raw = sessionStorage.getItem(SESSION_KEY);
		const level = raw === null ? NaN : Number(raw);
		return isLevel(level) ? level : null;
	} catch {
		return null;
	}
}

export function currentOverviewSize(): number {
	return sessionOverviewSize() ?? clampLevel(config.overviewSize);
}

export function setSessionOverviewSize(level: number) {
	try {
		sessionStorage.setItem(SESSION_KEY, String(clampLevel(level)));
	} catch {
		// Storage unavailable: the size holds while the overview stays open.
	}
}

// Drops the session's own size so the saved default applies again.
export function clearSessionOverviewSize() {
	try {
		sessionStorage.removeItem(SESSION_KEY);
	} catch {
		// Nothing stored to clear.
	}
}
