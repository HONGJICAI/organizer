<script lang="ts">
	import { onMount } from 'svelte';
	import { innerWidth } from 'svelte/reactivity/window';
	import { paginationShown } from '$lib/pagination';
	import { PaginationNav } from 'carbon-components-svelte';
	import { Comic, Image } from '$lib/model.svelte';
	import { pageApiUrl } from '$lib/reader';
	import { viewerState } from '$lib/viewerState.svelte';
	import { Layer, registerHotkeys } from '$lib/hotkeys';
	import {
		OVERVIEW_SIZES,
		batchOf,
		clampLevel,
		currentOverviewSize,
		setSessionOverviewSize,
		thumbRequestWidth
	} from '$lib/overviewSize';

	interface Props {
		file: Comic | Image;
		// Jump the reader to a 1-based page and close the overview.
		onJump: (page: number) => void;
		onClose: () => void;
	}
	let { file, onJump, onClose }: Props = $props();

	// Thumbnail size level (S…XL): this session's choice, else the saved default.
	let level = $state(currentOverviewSize());
	const size = $derived(OVERVIEW_SIZES[level]);
	// Only the current batch is mounted, so opening a huge album never fires
	// hundreds of image requests at once.
	const batchSize = $derived(size.batch);

	// Matches the phone breakpoint in the styles below, where tiles go by column
	// count instead of minimum width.
	const MOBILE_QUERY = '(max-width: 672px)';
	let mobile = $state(false);
	let viewportWidth = $state(1024);
	let pixelRatio = $state(1);

	// Server-side render width: the drawn tile width at this level, snapped to a
	// few fixed widths (see thumbRequestWidth) so the browser cache keeps hitting.
	const thumbWidth = $derived(
		thumbRequestWidth(mobile ? viewportWidth / size.mobileColumns : size.thumb, pixelRatio)
	);

	const maxPage = $derived(file.page ?? 0);
	const totalBatches = $derived(Math.max(1, Math.ceil(maxPage / batchSize)));

	// Open on the batch holding the page the reader is on.
	// svelte-ignore state_referenced_locally
	let batch = $state(batchOf(viewerState.page, OVERVIEW_SIZES[level].batch));
	// Keep the batch valid if the page count shrinks (e.g. an album deletion).
	$effect(() => {
		if (batch > totalBatches) batch = totalBatches;
	});

	const start = $derived((batch - 1) * batchSize);
	const pages = $derived(
		Array.from(
			{ length: Math.max(0, Math.min(batchSize, maxPage - start)) },
			(_, i) => start + i + 1
		)
	);

	let grid: HTMLDivElement | null = $state(null);
	// Page to center once the grid re-renders: the reader's page on open, the
	// page that was in the middle when the size changes. Otherwise a batch change
	// from the pager starts at the top.
	let pendingAnchor: number | null = Math.max(viewerState.page, 1);

	$effect(() => {
		void pages;
		void level;
		if (!grid) return;
		if (pendingAnchor !== null) {
			const tile = grid.querySelector<HTMLElement>(`.overview-tile[data-page="${pendingAnchor}"]`);
			tile?.scrollIntoView({ block: 'center' });
			// Focus it too, so arrow keys and Enter start from there.
			tile?.focus({ preventScroll: true });
			pendingAnchor = null;
		} else {
			grid.scrollTo({ top: 0 });
		}
	});

	// The tile nearest the middle of the grid, to keep in view across a resize.
	function middlePage(): number {
		if (!grid) return pages[0] ?? 1;
		const box = grid.getBoundingClientRect();
		const midY = box.top + box.height / 2;
		const midX = box.left + box.width / 2;
		let best = pages[0] ?? 1;
		let bestDist = Infinity;
		for (const tile of grid.querySelectorAll<HTMLElement>('.overview-tile')) {
			const r = tile.getBoundingClientRect();
			const dist = Math.hypot(r.top + r.height / 2 - midY, r.left + r.width / 2 - midX);
			if (dist < bestDist) {
				bestDist = dist;
				best = Number(tile.dataset.page);
			}
		}
		return best;
	}

	function setLevel(next: number) {
		next = clampLevel(next);
		if (next === level) return;
		const anchor = middlePage();
		level = next;
		setSessionOverviewSize(next);
		pendingAnchor = anchor;
		batch = batchOf(anchor, OVERVIEW_SIZES[next].batch);
	}

	const tiles = () =>
		grid ? Array.from(grid.querySelectorAll<HTMLElement>('.overview-tile')) : [];

	// Columns the grid currently lays out, for moving a row up or down.
	function columns(): number {
		if (!grid) return 1;
		return getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length || 1;
	}

	// Arrow keys move the focused tile (Enter opens it, as the tiles are
	// buttons). Moving past the batch's first or last tile goes on into the
	// neighbouring batch.
	function moveFocus(delta: number) {
		const list = tiles();
		const from = list.indexOf(document.activeElement as HTMLElement);
		if (from === -1) {
			// Nothing focused yet: the first press picks the reader's page.
			const current = list.find((t) => Number(t.dataset.page) === viewerState.page) ?? list[0];
			current?.focus();
			return;
		}
		const target = pages[from] + delta;
		if (target < 1 || target > maxPage) return;
		const inBatch = list[from + delta];
		if (inBatch) {
			inBatch.focus();
			inBatch.scrollIntoView({ block: 'nearest' });
		} else {
			pendingAnchor = target;
			batch = batchOf(target, batchSize);
		}
	}

	// PageDown/PageUp page through the batch a screen at a time, like a page
	// scroll, and only move to the next/previous batch from its bottom/top, so
	// paging from start to end shows every tile. The screen moves to the first
	// row cut off at the bottom (or, going back, puts the last row cut off at the
	// top just above the bottom edge), and focus goes to that row so arrows and
	// Enter carry on from what is in view.
	function pageScroll(delta: 1 | -1) {
		if (!grid) return;
		const atEdge =
			delta > 0 ? grid.scrollTop >= grid.scrollHeight - grid.clientHeight - 2 : grid.scrollTop <= 2;
		if (atEdge) {
			const next = batch + delta;
			if (next < 1 || next > totalBatches) return;
			// Centering a first/last tile clamps to the top/bottom of its batch.
			pendingAnchor = delta > 0 ? (next - 1) * batchSize + 1 : Math.min(next * batchSize, maxPage);
			batch = next;
			return;
		}
		const box = grid.getBoundingClientRect();
		const style = getComputedStyle(grid);
		const padTop = parseFloat(style.paddingTop) || 0;
		const padBottom = parseFloat(style.paddingBottom) || 0;
		const list = tiles();
		let target: HTMLElement | undefined;
		let by: number;
		if (delta > 0) {
			target = list.find((t) => t.getBoundingClientRect().bottom > box.bottom - padBottom + 1);
			by = target ? target.getBoundingClientRect().top - box.top - padTop : grid.clientHeight;
		} else {
			target = list.filter((t) => t.getBoundingClientRect().top < box.top + padTop - 1).pop();
			by = target
				? target.getBoundingClientRect().bottom - (box.bottom - padBottom)
				: -grid.clientHeight;
		}
		grid.scrollBy({ top: by, behavior: 'instant' });
		target?.focus({ preventScroll: true });
	}

	// Ctrl + wheel (and trackpad pinch, which browsers report as one) resizes
	// the tiles instead of zooming the page. One step per gesture burst, so a
	// single flick doesn't run straight from S to XL.
	let wheelLockedUntil = 0;
	function handleWheel(e: WheelEvent) {
		if (!e.ctrlKey && !e.metaKey) return;
		e.preventDefault();
		const now = performance.now();
		if (now < wheelLockedUntil || e.deltaY === 0) return;
		wheelLockedUntil = now + 250;
		setLevel(level + (e.deltaY < 0 ? 1 : -1));
	}

	onMount(() => {
		const media = window.matchMedia(MOBILE_QUERY);
		const measure = () => {
			mobile = media.matches;
			viewportWidth = window.innerWidth;
			pixelRatio = window.devicePixelRatio || 1;
		};
		measure();
		const unregister = registerHotkeys(Layer.Overlay, [
			{ keys: ['Escape', 'o'], description: 'Close the overview', run: onClose },
			{ keys: ['+', '='], description: 'Larger thumbnails', run: () => setLevel(level + 1) },
			{ keys: ['-', '_'], description: 'Smaller thumbnails', run: () => setLevel(level - 1) },
			{ keys: ['ArrowLeft'], description: 'Previous page', run: () => moveFocus(-1), repeat: true },
			{ keys: ['ArrowRight'], description: 'Next page', run: () => moveFocus(1), repeat: true },
			{
				keys: ['ArrowUp'],
				description: 'Page above',
				run: () => moveFocus(-columns()),
				repeat: true
			},
			{
				keys: ['ArrowDown'],
				description: 'Page below',
				run: () => moveFocus(columns()),
				repeat: true
			},
			{
				keys: ['PageUp'],
				description: 'Previous screen, then previous batch',
				run: () => pageScroll(-1),
				repeat: true
			},
			{
				keys: ['PageDown'],
				description: 'Next screen, then next batch',
				run: () => pageScroll(1),
				repeat: true
			}
		]);
		window.addEventListener('resize', measure);
		// Not passive: preventDefault must stop the browser zoom.
		grid?.addEventListener('wheel', handleWheel, { passive: false });
		return () => {
			unregister();
			window.removeEventListener('resize', measure);
			grid?.removeEventListener('wheel', handleWheel);
		};
	});
</script>

<div class="overview-root">
	<div class="overview-bar">
		<span class="overview-title">{file.name}</span>
		<span class="overview-count">{maxPage} pages</span>
		<div class="overview-sizes" role="group" aria-label="Thumbnail size">
			{#each OVERVIEW_SIZES as s, i (s.label)}
				<button
					class="overview-size"
					class:active={i === level}
					aria-pressed={i === level}
					title={`Thumbnail size ${s.label} (+/− to change)`}
					onclick={() => setLevel(i)}>{s.label}</button
				>
			{/each}
		</div>
		<button class="overview-close" aria-label="Close overview" onclick={onClose}>✕</button>
	</div>
	<div
		class="overview-grid"
		bind:this={grid}
		style:--tile-min={`${size.minWidthRem}rem`}
		style:--mobile-columns={size.mobileColumns}
	>
		{#each pages as pageNum (pageNum)}
			<button
				class="overview-tile"
				class:current={pageNum === viewerState.page}
				data-page={pageNum}
				onclick={() => onJump(pageNum)}
			>
				<img
					src={pageApiUrl(file.type, file.id, pageNum, thumbWidth)}
					alt={`Page ${pageNum}`}
					loading="lazy"
				/>
				<span class="overview-num">{pageNum}</span>
			</button>
		{/each}
	</div>
	{#if totalBatches > 1}
		<div class="overview-pager">
			<PaginationNav
				bind:page={batch}
				total={totalBatches}
				shown={paginationShown(innerWidth.current)}
			/>
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

	.overview-sizes {
		flex-shrink: 0;
		display: flex;
		border: 1px solid var(--cds-ui-03, #3d3d3d);
		border-radius: 0.25rem;
		overflow: hidden;
	}

	.overview-size {
		min-width: 2rem;
		padding: 0.25rem 0.375rem;
		background: none;
		border: none;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.75rem;
		line-height: 1;
		cursor: pointer;
	}

	.overview-size + .overview-size {
		border-left: 1px solid var(--cds-ui-03, #3d3d3d);
	}

	.overview-size.active {
		background: var(--cds-interactive-01, #0f62fe);
		color: var(--cds-text-04, #ffffff);
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
		grid-template-columns: repeat(auto-fill, minmax(var(--tile-min, 7rem), 1fr));
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

	.overview-tile:focus-visible {
		outline: 2px solid var(--cds-focus, #ffffff);
		outline-offset: 2px;
	}

	.overview-tile.current {
		border-color: var(--cds-interactive-01, #0f62fe);
	}

	.overview-tile img {
		display: block;
		width: 100%;
		/* Roughly a manga page; spreads and odd sizes letterbox inside. */
		aspect-ratio: 0.7;
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
			grid-template-columns: repeat(var(--mobile-columns, 4), minmax(0, 1fr));
		}
	}
</style>
