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
	import { onMount } from 'svelte';
	import { Comic, Image, ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { pageApiUrl, viewModeClass } from '$lib/reader';
	import { viewerState } from '$lib/viewerState.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { ComicpageService } from '$lib/client';

	interface Props {
		file: Comic | Image;
	}
	let { file }: Props = $props();

	let comicTarget: HTMLImageElement | null = $state(null);
	let targets: ReadonlyArray<null | HTMLElement> = $derived([comicTarget]);

	let page = $state(1);
	let loading = $state(true);
	let pageError = $state(false);
	let pageRetry = $state(0);

	const maxPage = $derived(file.page ?? 0);
	const viewClass = $derived(viewModeClass(config.viewMode as ViewMode));
	const objUrl = $derived(pageApiUrl(file.type, file.id, page));
	const nextUrl = $derived(page + 1 <= maxPage ? pageApiUrl(file.type, file.id, page + 1) : '');

	// Reset the paged error whenever the page changes.
	$effect(() => {
		page;
		pageError = false;
	});

	// Drive the viewer chrome (title bar page counter, progress reporter).
	$effect(() => {
		viewerState.maxPage = maxPage;
		viewerState.page = page;
	});

	onMount(() => {
		window.scrollTo(0, 0);
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});

	const preloadImageAsync = (url: string) => {
		new Promise((resolve, reject) => {
			const img = new window.Image();
			img.onload = resolve;
			img.onerror = reject;
			img.src = url;
		});
	};

	const handleKeydown = (event: KeyboardEvent) => {
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
		const { error } = await ComicpageService.comicPageLike({ path: { id: file.id, page } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to like page' }));
		} else {
			addNotification(new SuccessNotification({ subtitle: 'Successfully liked page' }));
		}
	}

	async function onSetCover() {
		const { error } = await ComicpageService.comicPageSetCover({ path: { id: file.id, page } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to set as cover' }));
		} else {
			fetch(file.coverUrl, { cache: 'reload', mode: 'no-cors' });
			const cover = document.getElementById(file.coverId) as HTMLImageElement;
			if (cover) cover.src = file.coverUrl;
			addNotification(new SuccessNotification({ subtitle: 'Successfully set as cover' }));
		}
	}
</script>

<div class="viewer-root">
	<div class={viewClass}>
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
	</div>
	<ContextMenu target={targets}>
		<ContextMenuOption indented labelText="Like page" on:click={onLikePage} />
		<ContextMenuOption indented labelText="Set as Cover" on:click={onSetCover} />
		<ContextMenuDivider />
		<ContextMenuOption indented kind="danger" labelText="Delete" disabled />
	</ContextMenu>
</div>

<div class="bottom-bar">
	<PaginationNav bind:page total={maxPage} loop={true} shown={5} />
</div>

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

	/* Fill the same space the image would */
	.fit-to-height .page-error,
	.fit-to-width .page-error,
	.fit-to-contain .page-error {
		min-height: 50vh;
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

	/* Paged modes */
	.fit-to-height {
		overflow-x: hidden;
	}
	.fit-to-height img {
		height: calc(100vh - 6rem);
	}

	.fit-to-width {
		max-width: 100vw;
	}
	.fit-to-width img {
		width: 100vw;
	}

	.fit-to-contain img {
		max-height: calc(100vh - 6rem);
		max-width: 100vw;
		width: auto;
		height: auto;
	}

	img {
		display: block;
		margin-left: auto;
		margin-right: auto;
		-webkit-user-drag: none;
	}
</style>
