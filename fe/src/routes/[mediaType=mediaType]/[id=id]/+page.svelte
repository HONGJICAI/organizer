<script lang="ts">
	import FileContent from '$lib/components/FileContent.svelte';
	import { page } from '$app/state';
	let { data } = $props();
</script>

{#if data.file}
	<FileContent
		file={data.file}
		initialOverview={page.url.searchParams.get('overview') === '1'}
		onClose={() => {
			window.close();
		}}
	/>
{/if}
