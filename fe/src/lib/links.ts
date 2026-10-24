import { connectionState, type MockMode } from '$lib/connection.svelte';

// Links that open in a new tab. Mock mode lives only in the page that started
// it, so a new tab gets the URL params that start it again (?mock=1, &auth=1);
// mock data is seeded, so it shows the same items.

/** `path` with the params that start `mock` mode, or unchanged without it. */
export function withMockParams(path: string, mock: MockMode | null): string {
	if (!mock) return path;
	const url = new URL(path, 'http://x');
	url.searchParams.set('mock', '1');
	if (mock.auth) url.searchParams.set('auth', '1');
	return url.pathname + url.search + url.hash;
}

/** Where a page started in mock mode goes once connected: the same page, without the mock params. */
export function withoutMockParams(href: string): string {
	const url = new URL(href, 'http://x');
	url.searchParams.delete('mock');
	url.searchParams.delete('auth');
	return url.pathname + url.search + url.hash;
}

/** The href of a link with target="_blank". */
export const newTabHref = (path: string) => withMockParams(path, connectionState.mock);

/** Open `path` in a new tab (for buttons; prefer a link with newTabHref). */
export const openInNewTab = (path: string) => window.open(newTabHref(path), '_blank');
