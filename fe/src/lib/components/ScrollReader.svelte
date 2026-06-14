<script lang="ts">
	import { Button } from 'carbon-components-svelte';
	import { Renew, ImageReference } from 'carbon-icons-svelte';
	import { onMount, tick } from 'svelte';
	import { Comic, Image, MediaType } from '$lib/model.svelte';
	import { pageApiUrl } from '$lib/reader';
	import { viewerState } from '$lib/viewerState.svelte';

	interface Props {
		file: Comic | Image;
	}
	let { file }: Props = $props();

	const maxPage = $derived(file.page ?? 0);

	let loadedCount = $state(0);
	let sentinel = $state<HTMLElement | null>(null);
	let jumpInput = $state(1);
	let scrollErrors = $state(new Set<number>());

	$effect(() => {
		viewerState.maxPage = maxPage;
	});

	onMount(() => {
		loadedCount = Math.min(5, maxPage);
		viewerState.page = 1;
		window.scrollTo(0, 0);
	});

	// Sentinel observer — load 5 more pages when the user nears the bottom. The
	// guard lives inside the callback (not the effect body) so loadedCount/maxPage
	// are not reactive dependencies here: the effect only re-runs when the
	// sentinel appears/disappears, preventing a cascade where every batch fires
	// immediately.
	$effect(() => {
		if (!sentinel) return;
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

	async function jumpToPage(target: number) {
		const p = Math.max(1, Math.min(target, maxPage));
		if (loadedCount < p) {
			loadedCount = p;
			await tick();
		}
		const el = document.querySelector(`[data-page="${p}"]`);
		el?.scrollIntoView({ behavior: 'smooth' });
	}

	// Action: track which page is in the center of the viewport.
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
</script>

<div class="viewer-root">
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
</div>

<div class="bottom-bar">
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

	img {
		display: block;
		margin-left: auto;
		margin-right: auto;
		-webkit-user-drag: none;
	}
</style>
