/**
 * The API client's fetch. A request that gets no response at all (the
 * connection dropped, the server is unreachable, or a proxy's error page was
 * blocked as cross-origin) rejects in a plain fetch, and the generated client
 * passes that on, so every caller would need a try/finally to reset its busy
 * state; most don't, and a button stayed disabled for good. Here it becomes a
 * 503 response with a `{ msg }` body like the server's own errors, which the
 * client hands back as `error`. A deliberate abort still rejects.
 */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	try {
		return await globalThis.fetch(input, init);
	} catch (e) {
		if (e instanceof DOMException && e.name === 'AbortError') throw e;
		const reason = e instanceof Error ? e.message : String(e);
		return new Response(JSON.stringify({ msg: `Can't reach the server (${reason})` }), {
			status: 503,
			headers: { 'Content-Type': 'application/json' }
		});
	}
}
