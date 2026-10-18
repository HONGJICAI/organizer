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
		// Don't save this file's reading progress (even if the session-wide
		// private reading is off) until the user turns it off from the header.
		privateReading?: boolean;
		// 1-based page to open at (e.g. "Continue reading" on the home page).
		initialPage?: number;
	}
	let {
		file,
		onClose,
		initialOverview = false,
		privateReading = false,
		initialPage = 1
	}: Props = $props();

	// Set before any effect runs so the first page report already sees it.
	viewerState.privateReading = privateReading || viewerState.privateSession;

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

	// Original dimensions of the current page, fetched only while the header's
	// page info is shown (the reader may display a downscaled copy, so the
	// loaded <img> can't tell). Cached per page for this file.
	// Set false on unmount, so late responses don't land on the next file.
	let mounted = true;
	const requested = new Set<number>();
	$effect(() => {
		const page = viewerState.page;
		const pageInfo = adapters[file.type].pageInfo;
		if (!config.showPageInfo || !pageInfo || page < 1 || requested.has(page)) return;
		requested.add(page);
		pageInfo(file.id, page).then((result) => {
			if (!mounted) return;
			viewerState.pageInfos[page] = result.error === undefined ? result.data : null;
		});
	});

	// Only paged/scroll media (comics, image albums) have a page overview.
	const hasPages = $derived(file.type !== MediaType.Video);

	onMount(() => {
		viewerState.active = true;
		viewerState.title = file.name;
		viewerState.onClose = onClose;
		if (initialOverview && hasPages) viewerState.overviewOpen = true;
		// The reader registered gotoPage in its own onMount, which ran first.
		if (hasPages && initialPage > 1) viewerState.gotoPage(initialPage);
		// Page names and sizes for the header's page info; one cheap request
		// (sizes come from the archive's directory, nothing is decompressed).
		viewerState.pageDetails = [];
		viewerState.pageInfos = {};
		const detail = adapters[file.type].detail;
		if (hasPages && detail) {
			detail(file.id).then((result) => {
				if (mounted && result.error === undefined)
					viewerState.pageDetails = result.data.pageDetails;
			});
		}
		return () => {
			viewerState.active = false;
			viewerState.overviewOpen = false;
			reporter.flush();
			viewerState.privateReading = viewerState.privateSession;
			mounted = false;
			viewerState.pageDetails = [];
			viewerState.pageInfos = {};
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
