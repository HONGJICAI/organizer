<script lang="ts">
	import FileContent from '$lib/components/FileContent.svelte';
	let { data } = $props();
</script>

{#if data.file}
	<FileContent
		file={data.file}
		onClose={() => {
			window.close();
		}}
	/>
{/if}
