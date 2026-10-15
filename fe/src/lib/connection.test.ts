import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { refreshMediaFiles } = vi.hoisted(() => ({ refreshMediaFiles: vi.fn() }));
vi.mock('$lib/mediaStore', () => ({ refreshMediaFiles }));

import { config } from './config.svelte';
import {
	connect,
	connectionState,
	isBlockedMixedContent,
	normalizeServerUrl,
	probeServer,
	SERVER_ERRORS
} from './connection.svelte';

function respond(body: string, contentType: string, status = 200) {
	const fetch = vi.fn(
		async () => new Response(body, { status, headers: { 'Content-Type': contentType } })
	);
	vi.stubGlobal('fetch', fetch);
	return fetch;
}

beforeEach(() => {
	const store = new Map<string, string>();
	vi.stubGlobal('localStorage', {
		getItem: (k: string) => store.get(k) ?? null,
		setItem: (k: string, v: string) => store.set(k, v),
		removeItem: (k: string) => store.delete(k),
		clear: () => store.clear()
	});
	config.apiServer = '';
	connectionState.status = 'idle';
	refreshMediaFiles.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe('normalizeServerUrl', () => {
	it('accepts full http(s) addresses and trims trailing slashes', () => {
		expect(normalizeServerUrl(' https://nas.example:81/ ')).toBe('https://nas.example:81');
		expect(normalizeServerUrl('http://localhost:8001')).toBe('http://localhost:8001');
	});

	it('rejects partial and non-http addresses', () => {
		expect(normalizeServerUrl('abc')).toBeNull();
		expect(normalizeServerUrl('localhost:8001')).toBeNull();
		expect(normalizeServerUrl('ftp://nas.example')).toBeNull();
		expect(normalizeServerUrl('')).toBeNull();
	});
});

describe('probeServer', () => {
	it('accepts an Organizer status response', async () => {
		const fetch = respond('{"required": true}', 'application/json');
		expect(await probeServer('https://organizer.example')).toEqual({ ok: true, required: true });
		expect(fetch).toHaveBeenCalledWith('https://organizer.example/api/auth/status');
	});

	it('rejects an HTML page or an error status', async () => {
		respond('<!doctype html><html></html>', 'text/html');
		expect(await probeServer('https://frontend.example')).toEqual({
			ok: false,
			error: SERVER_ERRORS.notOrganizer
		});
		respond('{"msg": "Not Found"}', 'application/json', 404);
		expect((await probeServer('https://other.example')).ok).toBe(false);
	});

	it('reports an unreachable server', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new TypeError('Failed to fetch');
			})
		);
		expect(await probeServer('https://down.example')).toEqual({
			ok: false,
			error: SERVER_ERRORS.unreachable
		});
	});

	it('does not change the current connection', async () => {
		config.apiServer = 'https://current.example';
		respond('{"required": false}', 'application/json');
		await probeServer('https://other.example');
		expect(config.apiServer).toBe('https://current.example');
		expect(localStorage.getItem('organizer-server-url')).toBeNull();
	});
});

describe('connect', () => {
	it('connects to a real server and remembers it', async () => {
		respond('{"required": false}', 'application/json');
		expect(await connect('https://organizer.example/')).toBe(true);
		expect(connectionState.status).toBe('connected');
		expect(config.apiServer).toBe('https://organizer.example');
		expect(localStorage.getItem('organizer-server-url')).toBe('https://organizer.example');
		// Switching servers drops lists cached from the previous one.
		expect(refreshMediaFiles).toHaveBeenCalled();
	});

	it('rejects a partial address without making a request', async () => {
		const fetch = respond('{"required": false}', 'application/json');
		expect(await connect('abc')).toBe(false);
		expect(connectionState.error).toBe(SERVER_ERRORS.format);
		expect(fetch).not.toHaveBeenCalled();
	});

	it('leaves config and storage alone when the server is rejected', async () => {
		respond('<!doctype html><html></html>', 'text/html');
		expect(await connect('https://frontend.example')).toBe(false);
		expect(connectionState.status).toBe('idle');
		expect(connectionState.error).toBe(SERVER_ERRORS.notOrganizer);
		expect(config.apiServer).toBe('');
		expect(localStorage.getItem('organizer-server-url')).toBeNull();
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
