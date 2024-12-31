<script lang="ts">
	import FileContent from '$lib/components/FileContent.svelte';
	import type { MediaFile } from '$lib/model';

	export let data;
	$: file = data.file as MediaFile;
</script>

<FileContent
	{file}
	onClose={() => {
		window.close();
	}}
/>
