<script lang="ts">
	import 'carbon-components-svelte/css/g100.css';
	import Main from '$lib/components/Main.svelte';
	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();
</script>

<Main>
	{@render children?.()}
</Main>
