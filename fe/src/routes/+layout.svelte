<script lang="ts">
	import 'carbon-components-svelte/css/g100.css';
	import Main from '$lib/components/Main.svelte';
	import LoginModal from '$lib/components/LoginModal.svelte';
	import ConnectDialog from '$lib/components/ConnectDialog.svelte';
	import { setDesktopConfig, setMobileConfig, config } from '$lib/config.svelte';
	import { authState } from '$lib/auth.svelte';
	import { connectionState } from '$lib/connection.svelte';
	import { client } from '$lib/client/client.gen';
	import { apiFetch } from '$lib/apiFetch';

	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();

	// Before any page calls the API: failed connections come back as errors.
	client.setConfig({ fetch: apiFetch });

	$effect(() => {
		client.setConfig({ baseUrl: config.apiServer });
	});

	$effect(() => {
		if (window.innerWidth < 768) {
			setMobileConfig();
		} else {
			setDesktopConfig();
		}
	});
</script>

{#if connectionState.status !== 'connected'}
	<ConnectDialog />
{:else}
	<Main>
		{@render children?.()}
	</Main>

	{#if authState.required && !authState.token}
		<LoginModal />
	{/if}
{/if}
