import { afterEach, describe, expect, it, vi } from 'vitest';

function stubSessionStorage(initial: Record<string, string> = {}) {
	const store = new Map(Object.entries(initial));
	vi.stubGlobal('sessionStorage', {
		getItem: (k: string) => store.get(k) ?? null,
		setItem: (k: string, v: string) => store.set(k, v),
		removeItem: (k: string) => store.delete(k)
	});
	return store;
}

async function load() {
	vi.resetModules();
	return import('./viewerState.svelte');
}

afterEach(() => vi.unstubAllGlobals());

describe('private reading', () => {
	it('is off by default', async () => {
		stubSessionStorage();
		const { viewerState } = await load();
		expect(viewerState.privateSession).toBe(false);
		expect(viewerState.privateReading).toBe(false);
	});

	it('restores the session setting', async () => {
		stubSessionStorage({ 'organizer.privateReading': '1' });
		const { viewerState } = await load();
		expect(viewerState.privateSession).toBe(true);
		expect(viewerState.privateReading).toBe(true);
	});

	it('toggles the open file and the session together and persists', async () => {
		const store = stubSessionStorage();
		const { viewerState, setPrivateReading } = await load();
		setPrivateReading(true);
		expect(viewerState.privateReading).toBe(true);
		expect(viewerState.privateSession).toBe(true);
		expect(store.get('organizer.privateReading')).toBe('1');
		setPrivateReading(false);
		expect(viewerState.privateReading).toBe(false);
		expect(viewerState.privateSession).toBe(false);
		expect(store.has('organizer.privateReading')).toBe(false);
	});

	it('works without sessionStorage', async () => {
		vi.stubGlobal('sessionStorage', undefined);
		const { viewerState, setPrivateReading } = await load();
		expect(viewerState.privateSession).toBe(false);
		setPrivateReading(true);
		expect(viewerState.privateSession).toBe(true);
	});
});
