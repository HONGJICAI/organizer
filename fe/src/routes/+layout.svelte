<script lang="ts">
	import 'carbon-components-svelte/css/g100.css';
	import Main from '$lib/components/Main.svelte';
	import LoginModal from '$lib/components/LoginModal.svelte';
	import ConnectDialog from '$lib/components/ConnectDialog.svelte';
	import { setDesktopConfig, setMobileConfig, config } from '$lib/config.svelte';
	import { authState } from '$lib/auth.svelte';
	import { connectionState } from '$lib/connection.svelte';
	import { client } from '$lib/client/client.gen';

	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();

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
