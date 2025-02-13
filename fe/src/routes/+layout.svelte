<script lang="ts">
	import 'carbon-components-svelte/css/g100.css';
	import Main from '$lib/components/Main.svelte';
	import { setDesktopConfig, setMobileConfig } from '$lib/config.svelte';
	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();
	$effect(() => {
		if (window.innerWidth < 768) {
			setMobileConfig();
		} else {
			setDesktopConfig();
		}
	});
</script>

<Main>
	{@render children?.()}
</Main>
