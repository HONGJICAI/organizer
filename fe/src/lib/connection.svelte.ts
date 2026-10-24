import { client } from '$lib/client/client.gen';
import { AuthService } from '$lib/client/sdk.gen';
import { config } from '$lib/config.svelte';
import { authState } from '$lib/auth.svelte';
import { refreshMediaFiles } from '$lib/mediaStore';

export const SERVER_URL_KEY = 'organizer-server-url';

/** Set while the app runs on mock data (`auth`: login is simulated). */
export type MockMode = { auth: boolean };

class ConnectionState {
	status = $state<'idle' | 'connecting' | 'connected'>('idle');
	error = $state<string | null>(null);
	mock = $state<MockMode | null>(null);
}

export const connectionState = new ConnectionState();

// An https page can't call a plain-http server (mixed content), except one on
// this machine (localhost / 127.0.0.1), which browsers treat as secure.
export function isBlockedMixedContent(pageUrl: string, serverUrl: string): boolean {
	try {
		const page = new URL(pageUrl);
		const server = new URL(serverUrl, pageUrl);
		const local = ['localhost', '127.0.0.1', '[::1]'].includes(server.hostname);
		return page.protocol === 'https:' && server.protocol === 'http:' && !local;
	} catch {
		return false;
	}
}

export const SERVER_ERRORS = {
	format: 'Enter a full address, like https://host:port',
	mixedContent:
		'This page is https, so the browser blocks http:// servers. Use an https address for the server.',
	notOrganizer: 'That address answered, but it is not an Organizer server',
	unreachable: 'Could not connect to server'
} as const;

/** A full http(s) server address without trailing slashes, or null. */
export function normalizeServerUrl(input: string): string | null {
	const trimmed = input.trim().replace(/\/+$/, '');
	try {
		const url = new URL(trimmed);
		return url.protocol === 'http:' || url.protocol === 'https:' ? trimmed : null;
	} catch {
		return null;
	}
}

export type ProbeResult = { ok: true; required: boolean } | { ok: false; error: string };

/**
 * Check that `serverUrl` is a reachable Organizer server, without touching the
 * current connection. Expects a normalized address (see normalizeServerUrl).
 */
export async function probeServer(serverUrl: string): Promise<ProbeResult> {
	if (typeof window !== 'undefined' && isBlockedMixedContent(window.location.href, serverUrl)) {
		return { ok: false, error: SERVER_ERRORS.mixedContent };
	}
	let res: Response;
	try {
		res = await fetch(`${serverUrl}/api/auth/status`);
	} catch {
		return { ok: false, error: SERVER_ERRORS.unreachable };
	}
	// A host that isn't the backend (e.g. the frontend's own static host, which
	// rewrites every path to index.html) still answers, just not with this.
	const body = res.ok ? await res.json().catch(() => null) : null;
	if (typeof body?.required !== 'boolean') return { ok: false, error: SERVER_ERRORS.notOrganizer };
	return { ok: true, required: body.required };
}

/** Switch to a server that passed probeServer and remember it. */
export function applyServer(serverUrl: string, required: boolean) {
	// Lists cached from another server would show until the next refresh.
	if (serverUrl !== config.apiServer) refreshMediaFiles();
	config.apiServer = serverUrl;
	client.setConfig({ baseUrl: serverUrl });
	authState.required = required;
	localStorage.setItem(SERVER_URL_KEY, serverUrl);
	connectionState.mock = null;
	connectionState.error = null;
	connectionState.status = 'connected';
}

export async function connect(input: string): Promise<boolean> {
	const serverUrl = normalizeServerUrl(input);
	if (!serverUrl) {
		connectionState.status = 'idle';
		connectionState.error = SERVER_ERRORS.format;
		return false;
	}
	connectionState.status = 'connecting';
	connectionState.error = null;
	const probe = await probeServer(serverUrl);
	if (!probe.ok) {
		connectionState.status = 'idle';
		connectionState.error = probe.error;
		return false;
	}
	applyServer(serverUrl, probe.required);
	return true;
}

export async function connectMock(authRequired: boolean): Promise<boolean> {
	connectionState.status = 'connecting';
	connectionState.error = null;

	config.apiServer = '';
	client.setConfig({ baseUrl: '' });

	try {
		const { setupMock } = await import('$lib/mock');
		await setupMock(authRequired);

		const { data, error } = await AuthService.status();
		if (error || !data) throw new Error('Mock setup failed');
		authState.required = data.required;
		connectionState.mock = { auth: authRequired };
		connectionState.status = 'connected';
		return true;
	} catch {
		connectionState.status = 'idle';
		connectionState.error = 'Mock setup failed';
		return false;
	}
}
