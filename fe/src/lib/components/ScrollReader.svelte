<script lang="ts">
	import { Button } from 'carbon-components-svelte';
	import { Renew, ImageReference } from 'carbon-icons-svelte';
	import { onMount, tick } from 'svelte';
	import { Comic, Image, InfoNotification, MediaType } from '$lib/model.svelte';
	import { addNotificationOnce } from '$lib/state.svelte';
	import { Layer, registerHotkeys } from '$lib/hotkeys';
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

	// Only pages near the screen keep their image. Every page loaded so far
	// stays in the DOM, so without this a long comic held all of its images
	// and kept growing (about 1.5 GB for 400 scan-sized pages in Chromium),
	// enough for a phone to kill the tab. A page further than NEAR_SCREENS
	// screens away whose size is known (it loaded once) becomes an empty slot
	// of the same height, so nothing moves; scrolling back reloads it from the
	// browser cache. A page that never loaded keeps its image so it gets a size.
	const NEAR_SCREENS = 3;
	// Height / width of each page that has loaded.
	let ratios = $state<Record<number, number>>({});
	let near = $state(new Set<number>());
	const showImage = (pageNum: number) => near.has(pageNum) || !(pageNum in ratios);

	$effect(() => {
		viewerState.maxPage = maxPage;
	});

	let nearObserver: IntersectionObserver | undefined;

	// Action: keep `near` up to date for a page's slot.
	function watchNear(node: HTMLElement) {
		nearObserver?.observe(node);
		return { destroy: () => nearObserver?.unobserve(node) };
	}

	function pageLoaded(pageNum: number, img: HTMLImageElement) {
		if (img.naturalWidth > 0) ratios[pageNum] = img.naturalHeight / img.naturalWidth;
		loadMore();
	}

	onMount(() => {
		nearObserver = new IntersectionObserver(
			(entries) => {
				const next = new Set(near);
				for (const e of entries) {
					const pageNum = Number((e.target as HTMLElement).dataset.page);
					if (e.isIntersecting) next.add(pageNum);
					else next.delete(pageNum);
				}
				near = next;
			},
			{ rootMargin: `${NEAR_SCREENS * 100}% 0px` }
		);
		loadedCount = Math.min(BATCH, maxPage);
		viewerState.page = 1;
		window.scrollTo(0, 0);
		// Let the overview grid jump us to a page.
		viewerState.gotoPage = (p: number) => jumpToPage(p);
		// No End key: page heights are unknown until images load, so a long jump
		// lands short once the pages above it load (overview jumps do too).
		const unregister = registerHotkeys(Layer.Reader, [
			{ keys: ['ArrowLeft'], description: 'Previous page', run: () => stepPage(-1), repeat: true },
			{ keys: ['ArrowRight'], description: 'Next page', run: () => stepPage(1), repeat: true },
			{ keys: ['Home'], description: 'First page', run: () => jumpToPage(1, false) }
		]);
		return () => {
			unregister();
			nearObserver?.disconnect();
		};
	});

	// Load the next batch of pages as the end of the loaded ones comes near
	// (within 400px). Checked when the sentinel enters that range and again
	// whenever a page finishes loading: a page has no height until its image
	// loads, so the sentinel stays in range while a batch loads (an observer
	// alone wouldn't fire again then), and short pages can leave it in range
	// after they load. Waiting for the batch keeps unsized pages from pulling
	// in the whole comic at once.
	const BATCH = 5;
	const AHEAD = 400;

	function loadMore() {
		if (!sentinel || loadedCount >= maxPage) return;
		if (sentinel.getBoundingClientRect().top > window.innerHeight + AHEAD) return;
		const pending = Array.from(
			document.querySelectorAll<HTMLImageElement>('.fit-to-scroll img.scroll-page')
		).some((img) => !img.complete);
		if (pending) return;
		loadedCount = Math.min(loadedCount + BATCH, maxPage);
	}

	$effect(() => {
		const node = sentinel;
		if (!node) return;
		const obs = new IntersectionObserver(([entry]) => entry.isIntersecting && loadMore(), {
			rootMargin: `${AHEAD}px`
		});
		obs.observe(node);
		return () => obs.disconnect();
	});

	// Keys step by what is on screen, not by the page counter: the counter is
	// whichever page crosses the middle of the viewport, which is ambiguous when
	// pages are short. Next is the first page starting below the top edge,
	// previous the last one starting above it. Jumps are instant, so a held key
	// doesn't aim at pages a smooth scroll hasn't reached yet.
	function pageElements(): HTMLElement[] {
		return Array.from(document.querySelectorAll<HTMLElement>('.fit-to-scroll [data-page]'));
	}

	async function stepPage(delta: 1 | -1) {
		const els = pageElements();
		if (delta < 0) {
			const prev = els.filter((el) => el.getBoundingClientRect().top < -1).pop();
			prev?.scrollIntoView({ behavior: 'instant' });
			return;
		}
		const root = document.documentElement;
		const atBottom = window.scrollY + window.innerHeight >= root.scrollHeight - 2;
		const next = els.find((el) => el.getBoundingClientRect().top > 1);
		if (loadedCount >= maxPage && (atBottom || !next)) {
			addNotificationOnce(
				new InfoNotification({ title: 'Last page', subtitle: `${file.name} has ${maxPage} pages` })
			);
			return;
		}
		if (next) next.scrollIntoView({ behavior: 'instant' });
		else await jumpToPage(loadedCount + 1, false);
	}

	async function jumpToPage(target: number, smooth = true) {
		const p = Math.max(1, Math.min(target, maxPage));
		if (loadedCount < p) {
			loadedCount = p;
			await tick();
		}
		const el = document.querySelector(`[data-page="${p}"]`);
		el?.scrollIntoView({ behavior: smooth ? 'smooth' : 'instant' });
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
		{#each Array.from({ length: loadedCount }, (_, i) => i + 1) as pageNum (pageNum)}
			<div
				class="scroll-slot"
				data-page={pageNum}
				use:trackPage={pageNum}
				use:watchNear
				style:aspect-ratio={!scrollErrors.has(pageNum) && !showImage(pageNum)
					? `1 / ${ratios[pageNum]}`
					: undefined}
			>
				{#if scrollErrors.has(pageNum)}
					<div class="page-error scroll-page-error">
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
				{:else if showImage(pageNum)}
					<img
						src={pageApiUrl(file.type, file.id, pageNum)}
						alt={`Page ${pageNum}`}
						class="scroll-page"
						onload={(e) => pageLoaded(pageNum, e.currentTarget as HTMLImageElement)}
						onerror={() => {
							scrollErrors = new Set([...scrollErrors, pageNum]);
							tick().then(loadMore);
						}}
					/>
				{/if}
			</div>
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

	.scroll-slot {
		margin-bottom: 2px;
	}

	.scroll-page {
		width: 100%;
		height: auto;
		display: block;
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
