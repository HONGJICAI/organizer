import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from './apiFetch';

describe('apiFetch', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('passes responses through', async () => {
		const res = new Response('{}', { status: 404 });
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res));
		expect(await apiFetch('/api/x')).toBe(res);
	});

	it('turns a failed connection into a 503 with a message', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
		const res = await apiFetch('/api/x');
		expect(res.status).toBe(503);
		expect(await res.json()).toEqual({ msg: "Can't reach the server (Failed to fetch)" });
	});

	it('keeps an abort a rejection', async () => {
		const abort = new DOMException('The user aborted a request.', 'AbortError');
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
		await expect(apiFetch('/api/x')).rejects.toBe(abort);
	});
});
