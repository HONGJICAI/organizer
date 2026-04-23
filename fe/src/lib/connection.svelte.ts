import { client } from '$lib/client/client.gen';
import { config } from '$lib/config.svelte';
import { authState } from '$lib/auth.svelte';

export const SERVER_URL_KEY = 'organizer-server-url';

class ConnectionState {
	status = $state<'idle' | 'connecting' | 'connected'>('idle');
	error = $state<string | null>(null);
}

export const connectionState = new ConnectionState();

export async function connect(serverUrl: string): Promise<boolean> {
	connectionState.status = 'connecting';
	connectionState.error = null;

	config.apiServer = serverUrl;
	client.setConfig({ baseUrl: serverUrl });

	try {
		const r = await fetch(`${serverUrl}/api/auth/status`);
		if (!r.ok) throw new Error('Server error');
		const data = (await r.json()) as { required: boolean };
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

		const r = await fetch('/api/auth/status');
		if (!r.ok) throw new Error('Mock setup failed');
		const data = (await r.json()) as { required: boolean };
		authState.required = data.required;
		connectionState.status = 'connected';
		return true;
	} catch {
		connectionState.status = 'idle';
		connectionState.error = 'Mock setup failed';
		return false;
	}
}
