import { client } from '$lib/client/client.gen';
import { config } from '$lib/config.svelte';

export const ssr = false;
export const prerender = false;

client.setConfig({
	baseUrl: config.apiServer
});
