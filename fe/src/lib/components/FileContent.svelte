<script lang="ts">
	import { onMount } from 'svelte';
	import { MediaType, Comic, Image, Video, type MediaFile } from '$lib/model.svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { viewerState } from '$lib/viewerState.svelte';
	import { createProgressReporter } from '$lib/readingProgress';
	import { adapters } from '$lib/mediaAdapters';
	import PagedReader from './PagedReader.svelte';
	import ScrollReader from './ScrollReader.svelte';
	import VideoPlayer from './VideoPlayer.svelte';
	import PageOverview from './PageOverview.svelte';

	interface Props {
		file: MediaFile;
		onClose: () => void;
		// Open straight into the page overview (e.g. from the duplicate finder).
		initialOverview?: boolean;
		// Don't save reading progress until the user turns it on from the header.
		privateReading?: boolean;
	}
	let { file, onClose, initialOverview = false, privateReading = false }: Props = $props();

	// Set before any effect runs so the first page report already sees it.
	viewerState.privateReading = privateReading;

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
	const reporter = createProgressReporter(file, 1000, () => !viewerState.privateReading);
	$effect(() => {
		// Reading privateReading here re-reports the current page as soon as
		// saving is turned on.
		if (viewerState.maxPage >= 1 && !viewerState.privateReading)
			reporter.schedule(viewerState.page);
	});

	// Only paged/scroll media (comics, image albums) have a page overview.
	const hasPages = $derived(file.type !== MediaType.Video);

	onMount(() => {
		viewerState.active = true;
		viewerState.title = file.name;
		viewerState.onClose = onClose;
		if (initialOverview && hasPages) viewerState.overviewOpen = true;
		// Page names and sizes for the header's page info; one cheap request
		// (sizes come from the archive's directory, nothing is decompressed).
		viewerState.pageDetails = [];
		let open = true;
		const detail = adapters[file.type].detail;
		if (hasPages && detail) {
			detail(file.id).then((result) => {
				if (open && result.error === undefined) viewerState.pageDetails = result.data.pageDetails;
			});
		}
		return () => {
			viewerState.active = false;
			viewerState.overviewOpen = false;
			reporter.flush();
			viewerState.privateReading = false;
			open = false;
			viewerState.pageDetails = [];
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

{#if hasPages && viewerState.overviewOpen}
	<PageOverview
		file={file as Comic | Image}
		onJump={(p) => {
			viewerState.gotoPage(p);
			viewerState.overviewOpen = false;
		}}
		onClose={() => (viewerState.overviewOpen = false)}
	/>
{/if}
