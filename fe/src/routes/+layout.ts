import { setupAuthInterceptors } from '$lib/auth.svelte';

export const ssr = false;
export const prerender = false;

export function load() {
	setupAuthInterceptors();
}
