<script lang="ts">
	import { onMount } from 'svelte';
	import { PaginationNav } from 'carbon-components-svelte';
	import { Comic, Image } from '$lib/model.svelte';
	import { pageApiUrl } from '$lib/reader';
	import { viewerState } from '$lib/viewerState.svelte';

	interface Props {
		file: Comic | Image;
		// Jump the reader to a 1-based page and close the overview.
		onJump: (page: number) => void;
		onClose: () => void;
	}
	let { file, onJump, onClose }: Props = $props();

	// Server-side thumbnail width. Small enough to render hundreds of pages
	// cheaply; the backend caps and aspect-preserves via the `width` param.
	const THUMB_WIDTH = 200;
	// Thumbnails rendered per overview screen. Only the current batch is mounted,
	// so opening a huge album never fires hundreds of image requests at once.
	const BATCH_SIZE = 60;

	const maxPage = $derived(file.page ?? 0);
	const totalBatches = $derived(Math.max(1, Math.ceil(maxPage / BATCH_SIZE)));

	// Open on the batch holding the page the reader is on.
	let batch = $state(Math.floor((Math.max(viewerState.page, 1) - 1) / BATCH_SIZE) + 1);
	// Keep the batch valid if the page count shrinks (e.g. an album deletion).
	$effect(() => {
		if (batch > totalBatches) batch = totalBatches;
	});

	const start = $derived((batch - 1) * BATCH_SIZE);
	const pages = $derived(
		Array.from({ length: Math.min(BATCH_SIZE, maxPage - start) }, (_, i) => start + i + 1)
	);

	let grid: HTMLDivElement | null = $state(null);
	let firstScrollDone = false;

	// On open, center the current page; on later batch changes, jump back to top.
	$effect(() => {
		batch;
		if (!grid) return;
		if (firstScrollDone) {
			grid.scrollTo({ top: 0 });
		} else {
			firstScrollDone = true;
			grid.querySelector('.overview-tile.current')?.scrollIntoView({ block: 'center' });
		}
	});

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});
</script>

<div class="overview-root">
	<div class="overview-bar">
		<span class="overview-title">{file.name}</span>
		<span class="overview-count">{maxPage} pages</span>
		<button class="overview-close" aria-label="Close overview" onclick={onClose}>✕</button>
	</div>
	<div class="overview-grid" bind:this={grid}>
		{#each pages as pageNum (pageNum)}
			<button
				class="overview-tile"
				class:current={pageNum === viewerState.page}
				onclick={() => onJump(pageNum)}
			>
				<img
					src={pageApiUrl(file.type, file.id, pageNum, THUMB_WIDTH)}
					alt={`Page ${pageNum}`}
					loading="lazy"
				/>
				<span class="overview-num">{pageNum}</span>
			</button>
		{/each}
	</div>
	{#if totalBatches > 1}
		<div class="overview-pager">
			<PaginationNav bind:page={batch} total={totalBatches} shown={5} />
		</div>
	{/if}
</div>

<style>
	.overview-root {
		position: fixed;
		inset: 0;
		z-index: 9000;
		background: var(--cds-ui-background, #161616);
		display: flex;
		flex-direction: column;
	}

	.overview-bar {
		flex-shrink: 0;
		height: 3rem;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0 1rem;
		background: var(--cds-ui-01, #262626);
		border-bottom: 1px solid var(--cds-ui-03, #3d3d3d);
	}

	.overview-title {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.overview-count {
		flex-shrink: 0;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-03, #8d8d8d);
	}

	.overview-close {
		flex-shrink: 0;
		background: none;
		border: none;
		color: var(--cds-text-01, #f4f4f4);
		font-size: 1rem;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
		line-height: 1;
	}

	.overview-grid {
		flex: 1;
		overflow-y: auto;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		grid-auto-rows: min-content;
		gap: 0.5rem;
		padding: 0.75rem;
	}

	.overview-pager {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--cds-ui-01, #262626);
		border-top: 1px solid var(--cds-ui-03, #3d3d3d);
	}

	.overview-tile {
		position: relative;
		display: block;
		padding: 0;
		border: 2px solid transparent;
		border-radius: 0.25rem;
		background: var(--cds-ui-01, #262626);
		cursor: pointer;
		overflow: hidden;
	}

	.overview-tile.current {
		border-color: var(--cds-interactive-01, #0f62fe);
	}

	.overview-tile img {
		display: block;
		width: 100%;
		height: 12rem;
		object-fit: contain;
		background: #000;
		-webkit-user-drag: none;
	}

	.overview-num {
		position: absolute;
		bottom: 0.25rem;
		right: 0.25rem;
		font-size: 0.6875rem;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-04, #ffffff);
		background: rgba(0, 0, 0, 0.6);
		padding: 0 0.375rem;
		border-radius: 0.75rem;
	}

	@media screen and (max-width: 672px) {
		.overview-grid {
			grid-template-columns: repeat(auto-fill, minmax(5rem, 1fr));
		}
		.overview-tile img {
			height: 8rem;
		}
	}
</style>
