import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { connect, connectionState, isBlockedMixedContent } from './connection.svelte';

function respond(body: string, contentType: string, status = 200) {
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => new Response(body, { status, headers: { 'Content-Type': contentType } }))
	);
}

describe('connect', () => {
	beforeEach(() => {
		const store = new Map<string, string>();
		vi.stubGlobal('localStorage', {
			getItem: (k: string) => store.get(k) ?? null,
			setItem: (k: string, v: string) => store.set(k, v),
			removeItem: (k: string) => store.delete(k),
			clear: () => store.clear()
		});
	});
	afterEach(() => vi.unstubAllGlobals());

	it('rejects a server that answers the API with an HTML page', async () => {
		// What the standalone frontend's own host does: every path is rewritten to index.html.
		respond('<!doctype html><html></html>', 'text/html');
		expect(await connect('https://frontend.example')).toBe(false);
		expect(connectionState.status).toBe('idle');
		expect(connectionState.error).toBe('That address answered, but it is not an Organizer server');
		expect(localStorage.getItem('organizer-server-url')).toBeNull();
	});

	it('connects to a real server and remembers it', async () => {
		respond('{"required": false}', 'application/json');
		expect(await connect('https://organizer.example')).toBe(true);
		expect(connectionState.status).toBe('connected');
		expect(localStorage.getItem('organizer-server-url')).toBe('https://organizer.example');
	});

	it('reports an unreachable server', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new TypeError('Failed to fetch');
			})
		);
		expect(await connect('https://down.example')).toBe(false);
		expect(connectionState.error).toBe('Could not connect to server');
	});
});

describe('isBlockedMixedContent', () => {
	const page = 'https://organizer.vercel.app/';

	it('blocks http servers from an https page', () => {
		expect(isBlockedMixedContent(page, 'http://192.168.1.10:81')).toBe(true);
	});

	it('allows https servers and this machine', () => {
		expect(isBlockedMixedContent(page, 'https://nas.example.ts.net')).toBe(false);
		expect(isBlockedMixedContent(page, 'http://localhost:81')).toBe(false);
		expect(isBlockedMixedContent(page, 'http://127.0.0.1:81')).toBe(false);
	});

	it('allows anything from an http page, and ignores unparsable input', () => {
		expect(isBlockedMixedContent('http://192.168.1.10:81/', 'http://192.168.1.20')).toBe(false);
		expect(isBlockedMixedContent(page, 'http://[bad')).toBe(false);
	});
});
