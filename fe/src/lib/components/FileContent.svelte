<script lang="ts">
	import { onMount } from 'svelte';
	import { MediaType, Comic, Image, Video, type MediaFile } from '$lib/model.svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { viewerState } from '$lib/viewerState.svelte';
	import { createProgressReporter } from '$lib/readingProgress';
	import PagedReader from './PagedReader.svelte';
	import ScrollReader from './ScrollReader.svelte';
	import VideoPlayer from './VideoPlayer.svelte';

	interface Props {
		file: MediaFile;
		onClose: () => void;
	}
	let { file, onClose }: Props = $props();

	const isScroll = $derived(config.viewMode === ViewMode.Scroll);

	// Video has no paged chrome; clear the title-bar page counter the previous
	// comic/image reader may have left on the shared viewer state.
	$effect(() => {
		if (file.type === MediaType.Video) {
			viewerState.page = 0;
			viewerState.maxPage = 0;
		}
	});

	// Reading-progress reporting is shared across the paged and scroll readers,
	// which both drive viewerState.page. Schedule a (debounced) report whenever
	// the settled page changes, and flush any pending one when the viewer closes.
	const reporter = createProgressReporter(file);
	$effect(() => {
		if (viewerState.maxPage >= 1) reporter.schedule(viewerState.page);
	});

	onMount(() => {
		viewerState.active = true;
		viewerState.title = file.name;
		viewerState.onClose = onClose;
		return () => {
			viewerState.active = false;
			reporter.flush();
		};
	});
</script>

{#if file.type === MediaType.Video}
	<VideoPlayer file={file as Video} />
{:else if isScroll}
	<ScrollReader file={file as Comic | Image} />
{:else}
	<PagedReader file={file as Comic | Image} />
{/if}
