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

export async function connect(serverUrl: string): Promise<boolean> {
	connectionState.status = 'connecting';
	connectionState.error = null;

	config.apiServer = serverUrl;
	client.setConfig({ baseUrl: serverUrl });

	try {
		const { data, error } = await AuthService.status();
		if (error || !data) throw new Error('Server error');
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
