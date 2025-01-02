<script lang="ts">
	import FileContent from '$lib/components/FileContent.svelte';
	import type { MediaFile } from '$lib/model.svelte';

	interface Props {
		data: any;
	}

	let { data }: Props = $props();
	let file = $state(data.file as MediaFile);
</script>

<FileContent
	{file}
	onClose={() => {
		window.close();
	}}
/>
