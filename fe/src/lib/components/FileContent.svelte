<script lang="ts">
	import {
		ContextMenu,
		ContextMenuDivider,
		ContextMenuOption,
		PaginationNav,
		ProgressBar,
		Button
	} from 'carbon-components-svelte';
	import { Renew, ImageReference } from 'carbon-icons-svelte';
	import {
		Comic,
		ErrorNotification,
		Image,
		MediaFile,
		MediaType,
		SuccessNotification,
		Video
	} from '$lib/model.svelte';
	import { config, PageWidthMode, ViewMode } from '$lib/config.svelte';
	import { onMount, tick } from 'svelte';
	import { addNotification } from '$lib/state.svelte';
	import { viewerState } from '$lib/viewerState.svelte';
	import { ComicpageService, ImagesService } from '$lib/client';
	import { authState } from '$lib/auth.svelte';

	interface Props {
		file: MediaFile;
		onClose: () => void;
	}

	let { file, onClose }: Props = $props();
	let comicTarget: null | HTMLImageElement = $state(null);
	let targets: ReadonlyArray<null | HTMLElement> = $derived([comicTarget]);
	let videoTarget: null | HTMLVideoElement = $state(null);
	let maxPage = $state(0);
	let loading = $state(true);
	let page = $state(1);
	let objUrl = $state('');
	let nextUrl = $state('');
	let videoTime = $state(0);
	let duration = $state(9999999);

	// Scroll mode state
	let loadedCount = $state(5);
	let sentinel = $state<HTMLElement | null>(null);
	let jumpInput = $state(1);

	// Error state
	let pageError = $state(false);
	let pageRetry = $state(0);
	let scrollErrors = $state(new Set<number>());

	// Reset paged error on page change
	$effect(() => {
		page;
		pageError = false;
	});

	const comicViewMode = $derived.by(() => {
		switch (config.viewMode) {
			case ViewMode.Width:
				return 'fit-to-width';
			case ViewMode.Height:
				return 'fit-to-height';
			case ViewMode.Contain:
				return 'fit-to-contain';
			case ViewMode.Scroll:
				return 'fit-to-scroll';
		}
	});

	let comic = $derived(file as Comic);
	let image = $derived(file as Image);
	let video = $derived(file as Video);

	// Server-side page width cap, keep in sync with the backend's `width` query param.
	const MAX_PAGE_WIDTH = 4096;

	function pageWidth(): number | null {
		switch (config.pageWidthMode) {
			case PageWidthMode.Device:
				return Math.min(
					MAX_PAGE_WIDTH,
					Math.round(window.innerWidth * (window.devicePixelRatio || 1))
				);
			case PageWidthMode.Custom:
				return config.pageWidthCustom > 0
					? Math.min(MAX_PAGE_WIDTH, Math.round(config.pageWidthCustom))
					: null;
			default:
				return null;
		}
	}

	function pageApiUrl(mediaType: MediaType, id: number, pageNum: number): string {
		const base =
			mediaType === MediaType.Image
				? `${config.apiServer}/api/images/${id}/pages/${pageNum}`
				: `${config.apiServer}/api/comics/${id}/pages/${pageNum}`;
		const params = new URLSearchParams();
		if (authState.token) params.set('token', authState.token);
		const width = pageWidth();
		if (width) params.set('width', String(width));
		const qs = params.toString();
		return qs ? `${base}?${qs}` : base;
	}

	$effect(() => {
		switch (file.type) {
			case MediaType.Comic:
				maxPage = comic.page ?? 0;
				if (comicViewMode !== 'fit-to-scroll') {
					objUrl = pageApiUrl(MediaType.Comic, comic.id, page);
					nextUrl = page + 1 <= maxPage ? pageApiUrl(MediaType.Comic, comic.id, page + 1) : '';
				}
				break;
			case MediaType.Image:
				maxPage = image.page ?? 0;
				if (comicViewMode !== 'fit-to-scroll') {
					objUrl = pageApiUrl(MediaType.Image, image.id, page);
					nextUrl = page + 1 <= maxPage ? pageApiUrl(MediaType.Image, image.id, page + 1) : '';
				}
				break;
			case MediaType.Video:
				objUrl = `${config.apiServer}/videos/${video?.id}`;
				break;
		}
	});

	// Reset scroll state when entering scroll mode
	$effect(() => {
		if (
			comicViewMode === 'fit-to-scroll' &&
			maxPage > 0 &&
			(file.type === MediaType.Comic || file.type === MediaType.Image)
		) {
			loadedCount = Math.min(5, maxPage);
			viewerState.page = 1;
		}
	});

	// Sentinel observer — load 5 more pages when user nears the bottom.
	// Guard is inside the callback (not the effect body) so loadedCount/maxPage
	// are not reactive dependencies here — the effect only re-runs when sentinel
	// appears/disappears, preventing a cascade where every batch fires immediately.
	$effect(() => {
		if (!sentinel || comicViewMode !== 'fit-to-scroll') return;
		const obs = new IntersectionObserver(
			([entry]) => {
				if (entry.isIntersecting && loadedCount < maxPage) {
					loadedCount = Math.min(loadedCount + 5, maxPage);
				}
			},
			{ rootMargin: '400px' }
		);
		obs.observe(sentinel);
		return () => obs.disconnect();
	});

	// Sync viewerState
	$effect(() => {
		viewerState.maxPage = maxPage;
		if (comicViewMode !== 'fit-to-scroll') {
			viewerState.page = page;
		}
	});

	// Report reading progress, debounced so flipping through pages only sends
	// the position the reader settles on. The viewer flushes the pending
	// position on unmount, otherwise closing within the debounce window would
	// lose the last page read.
	let reportedPosition = 0;
	function reportProgress(position: number) {
		if (position === reportedPosition) return;
		if (position < 1 || maxPage < 1) return;
		if (file.type !== MediaType.Comic && file.type !== MediaType.Image) return;
		reportedPosition = position;
		const opts = { path: { id: file.id }, body: { position } };
		if (file.type === MediaType.Comic) {
			ComicpageService.comicPageUpdateProgress(opts);
		} else {
			ImagesService.imageUpdateProgress(opts);
		}
	}

	$effect(() => {
		const position = viewerState.page;
		const timer = setTimeout(() => reportProgress(position), 1000);
		return () => clearTimeout(timer);
	});

	onMount(() => {
		window.scrollTo(0, 0);
		window.addEventListener('keydown', handleKeydown);
		viewerState.active = true;
		viewerState.title = file.name;
		viewerState.onClose = onClose;
		return () => {
			window.removeEventListener('keydown', handleKeydown);
			viewerState.active = false;
			reportProgress(viewerState.page);
		};
	});

	async function jumpToPage(target: number) {
		const p = Math.max(1, Math.min(target, maxPage));
		if (loadedCount < p) {
			loadedCount = p;
			await tick();
		}
		const el = document.querySelector(`[data-page="${p}"]`);
		el?.scrollIntoView({ behavior: 'smooth' });
	}

	// Action: track which page is in the center of the viewport
	function trackPage(node: HTMLElement, pageNum: number) {
		const obs = new IntersectionObserver(
			([entry]) => {
				if (entry.isIntersecting) viewerState.page = pageNum;
			},
			{ rootMargin: '-40% 0px -40% 0px', threshold: 0 }
		);
		obs.observe(node);
		return { destroy: () => obs.disconnect() };
	}

	const preloadImageAsync = async (url: string) => {
		new Promise((resolve, reject) => {
			const img = new window.Image();
			img.onload = resolve;
			img.onerror = reject;
			img.src = url;
		});
	};

	const handleKeydown = (event: KeyboardEvent) => {
		if (comicViewMode === 'fit-to-scroll') return;
		if (event.key === 'ArrowLeft') {
			page = (page - 1 + maxPage) % maxPage;
		} else if (event.key === 'ArrowRight') {
			page = (page + 1) % maxPage;
		}
	};

	const goNextPage = () => {
		if (loading) return;
		loading = true;
		page = Math.min(page + 1, maxPage);
		window.scrollTo(0, 0);
	};

	const goPrevPage = () => {
		if (loading) return;
		loading = true;
		page = Math.max(page - 1, 1);
		window.scrollTo(0, 0);
	};

	function onClickImage(e: MouseEvent): void {
		const ct = e.currentTarget as HTMLElement;
		if (!ct) return;
		const { left, right } = ct.getBoundingClientRect();
		if (e.x < left + (right - left) / 2) {
			goPrevPage();
		} else {
			goNextPage();
		}
	}

	async function onLikePage() {
		if (!comic) return;
		const { error } = await ComicpageService.comicPageLike({
			path: { id: comic.id, page }
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to like page' }));
		} else {
			addNotification(new SuccessNotification({ subtitle: 'Successfully liked page' }));
		}
	}

	async function onSetCover() {
		if (!comic) return;
		const { error } = await ComicpageService.comicPageSetCover({
			path: { id: comic.id, page }
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to set as cover' }));
		} else {
			fetch(comic.coverUrl, { cache: 'reload', mode: 'no-cors' });
			const cover = document.getElementById(comic.coverId) as HTMLImageElement;
			if (cover) cover.src = comic.coverUrl;
			addNotification(new SuccessNotification({ subtitle: 'Successfully set as cover' }));
		}
	}
</script>

<div class="viewer-root">
	{#if (file.type === MediaType.Comic || file.type === MediaType.Image) && comicViewMode === 'fit-to-scroll'}
		<!-- Scroll mode: all pages stacked vertically with lazy loading -->
		<div class="fit-to-scroll">
			{#each Array.from({ length: loadedCount }, (_, i) => i + 1) as pageNum}
				{#if scrollErrors.has(pageNum)}
					<div class="page-error scroll-page-error" use:trackPage={pageNum} data-page={pageNum}>
						<ImageReference size={32} />
						<span>Page {pageNum} failed to load</span>
						<Button
							size="small"
							kind="ghost"
							icon={Renew}
							on:click={() => {
								scrollErrors.delete(pageNum);
								scrollErrors = new Set(scrollErrors);
							}}
						>
							Retry
						</Button>
					</div>
				{:else}
					<img
						use:trackPage={pageNum}
						data-page={pageNum}
						src={pageApiUrl(file.type, file.id, pageNum)}
						alt={`Page ${pageNum}`}
						class="scroll-page"
						onerror={() => {
							scrollErrors = new Set([...scrollErrors, pageNum]);
						}}
					/>
				{/if}
			{/each}
			{#if loadedCount < maxPage}
				<div bind:this={sentinel} class="load-sentinel">
					<span>Loading…</span>
				</div>
			{:else}
				<div class="scroll-end">End of {file.type === MediaType.Image ? 'album' : 'comic'}</div>
			{/if}
		</div>
	{:else}
		<!-- Paged mode -->
		<div class={comicViewMode}>
			{#if file.type === MediaType.Comic || file.type === MediaType.Image}
				<ProgressBar hideLabel max={maxPage} value={page} />
				<div onclick={onClickImage} role="none">
					{#if pageError}
						<div class="page-error">
							<ImageReference size={32} />
							<span>Page {page} failed to load</span>
							<Button
								size="small"
								kind="ghost"
								icon={Renew}
								on:click={(e) => {
									e.stopPropagation();
									pageError = false;
									pageRetry += 1;
								}}
							>
								Retry
							</Button>
						</div>
					{:else}
						<img
							bind:this={comicTarget}
							src={`${objUrl}${pageRetry > 0 ? `${objUrl.includes('?') ? '&' : '?'}r=${pageRetry}` : ''}`}
							alt="page content"
							onload={() => {
								loading = false;
								preloadImageAsync(nextUrl);
							}}
							onerror={() => {
								loading = false;
								pageError = true;
							}}
						/>
					{/if}
				</div>
			{/if}
			{#if file.type === MediaType.Video}
				<ProgressBar hideLabel max={duration} value={videoTime} />
				<video
					bind:this={videoTarget}
					src={objUrl}
					controls
					autoplay
					loop
					oncanplay={() => {
						loading = false;
					}}
					ontimeupdate={() => {
						if (videoTarget) {
							videoTime = videoTarget.currentTime;
							duration = videoTarget.duration;
						}
					}}
				>
					<track kind="captions" />
				</video>
			{/if}
		</div>
		<ContextMenu target={targets}>
			<ContextMenuOption indented labelText="Like page" on:click={onLikePage} />
			<ContextMenuOption indented labelText="Set as Cover" on:click={onSetCover} />
			<ContextMenuDivider />
			<ContextMenuOption indented kind="danger" labelText="Delete" disabled />
		</ContextMenu>
	{/if}
</div>

{#if file.type === MediaType.Comic || file.type === MediaType.Image}
	<div class="bottom-bar">
		{#if comicViewMode === 'fit-to-scroll'}
			<span class="jump-label">{viewerState.page} / {maxPage}</span>
			<input
				class="jump-input"
				type="number"
				min="1"
				max={maxPage}
				bind:value={jumpInput}
				onkeydown={(e) => {
					if (e.key === 'Enter') jumpToPage(jumpInput);
				}}
			/>
			<button class="jump-btn" onclick={() => jumpToPage(jumpInput)}>Go</button>
		{:else}
			<PaginationNav bind:page total={maxPage} loop={true} shown={5} />
		{/if}
	</div>
{/if}

<style>
	.viewer-root {
		user-select: none;
	}

	/* Error placeholder */
	.page-error {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		color: var(--cds-text-03, #6f6f6f);
		font-size: 0.875rem;
	}

	.page-error :global(svg) {
		color: var(--cds-text-03, #6f6f6f);
	}

	/* Paged mode: fill the same space as the image would */
	.fit-to-height .page-error,
	.fit-to-width .page-error,
	.fit-to-contain .page-error {
		min-height: 50vh;
	}

	/* Scroll mode error block */
	.scroll-page-error {
		width: 100%;
		min-height: 300px;
		background: var(--cds-ui-01, #262626);
		border-bottom: 2px solid var(--cds-ui-03, #3d3d3d);
	}

	/* Fixed bottom nav bar */
	.bottom-bar {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		height: 3rem;
		background: var(--cds-ui-01, #262626);
		border-top: 1px solid var(--cds-ui-03, #3d3d3d);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.bottom-bar :global(.bx--pagination-nav) {
		height: 3rem;
	}

	.jump-label {
		font-size: 0.875rem;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-02, #c6c6c6);
		margin-right: 0.75rem;
	}

	.jump-input {
		width: 4rem;
		height: 2rem;
		background: var(--cds-field-01, #393939);
		border: 1px solid var(--cds-ui-04, #8d8d8d);
		border-radius: 0.25rem;
		color: var(--cds-text-01, #f4f4f4);
		font-size: 0.875rem;
		text-align: center;
		padding: 0 0.25rem;
		margin-right: 0.5rem;
	}

	.jump-input:focus {
		outline: 2px solid var(--cds-focus, #0f62fe);
		outline-offset: -2px;
	}

	.jump-btn {
		height: 2rem;
		padding: 0 1rem;
		background: var(--cds-interactive-01, #0f62fe);
		color: var(--cds-text-04, #ffffff);
		border: none;
		border-radius: 0.25rem;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.jump-btn:hover {
		background: var(--cds-hover-primary, #0353e9);
	}

	/* Paged modes */
	.fit-to-height {
		overflow-x: hidden;
	}
	.fit-to-height img,
	.fit-to-height video {
		height: calc(100vh - 6rem);
	}

	.fit-to-width {
		max-width: 100vw;
	}
	.fit-to-width img,
	.fit-to-width video {
		width: 100vw;
	}

	.fit-to-contain img,
	.fit-to-contain video {
		max-height: calc(100vh - 6rem);
		max-width: 100vw;
		width: auto;
		height: auto;
	}

	/* Scroll mode */
	.fit-to-scroll {
		max-width: 1000px;
		margin: 0 auto;
		padding-bottom: 4rem;
	}

	.scroll-page {
		width: 100%;
		height: auto;
		display: block;
		margin-bottom: 2px;
	}

	.load-sentinel {
		padding: 2rem;
		text-align: center;
		color: var(--cds-text-03, #6f6f6f);
		font-size: 0.875rem;
	}

	.scroll-end {
		padding: 2rem;
		text-align: center;
		color: var(--cds-text-03, #6f6f6f);
		font-size: 0.875rem;
	}

	/* Shared */
	img,
	video {
		display: block;
		margin-left: auto;
		margin-right: auto;
		-webkit-user-drag: none;
	}
</style>
