import { client } from '$lib/client/client.gen';
import { AuthService } from '$lib/client/sdk.gen';
import { config } from '$lib/config.svelte';
import { authState } from '$lib/auth.svelte';

export const SERVER_URL_KEY = 'organizer-server-url';

class ConnectionState {
	status = $state<'idle' | 'connecting' | 'connected'>('idle');
	error = $state<string | null>(null);
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

export async function connect(serverUrl: string): Promise<boolean> {
	connectionState.status = 'connecting';
	connectionState.error = null;

	if (typeof window !== 'undefined' && isBlockedMixedContent(window.location.href, serverUrl)) {
		connectionState.status = 'idle';
		connectionState.error =
			'This page is https, so the browser blocks http:// servers. Use an https address for the server.';
		return false;
	}

	config.apiServer = serverUrl;
	client.setConfig({ baseUrl: serverUrl });

	try {
		const { data, error } = await AuthService.status();
		if (error || !data) throw new Error('Server error');
		// A host that isn't the backend (e.g. the frontend's own static host,
		// which rewrites every path to index.html) still answers 200, with HTML.
		if (typeof data.required !== 'boolean') {
			connectionState.status = 'idle';
			connectionState.error = 'That address answered, but it is not an Organizer server';
			return false;
		}
		authState.required = data.required;
		localStorage.setItem(SERVER_URL_KEY, serverUrl);
		connectionState.status = 'connected';
		return true;
	} catch {
		connectionState.status = 'idle';
		connectionState.error = 'Could not connect to server';
		return false;
	}
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
		connectionState.status = 'connected';
		return true;
	} catch {
		connectionState.status = 'idle';
		connectionState.error = 'Mock setup failed';
		return false;
	}
}
