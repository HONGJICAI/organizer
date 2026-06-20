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
	import {
		Comic,
		Image,
		MediaType,
		ErrorNotification,
		SuccessNotification
	} from '$lib/model.svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { pageApiUrl, viewModeClass } from '$lib/reader';
	import { viewerState } from '$lib/viewerState.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { ComicpageService, ImagesService } from '$lib/client';

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
	// Only the "contain" mode is zoom/pan capable: it has a fixed-height,
	// overflow-hidden stage so gesture handling never fights native scrolling.
	const zoomable = $derived(config.viewMode === ViewMode.Contain);
	const objUrl = $derived(pageApiUrl(file.type, file.id, page));
	const nextUrl = $derived(page + 1 <= maxPage ? pageApiUrl(file.type, file.id, page + 1) : '');

	// ----- Zoom & pan state (contain mode) -----
	let viewport: HTMLDivElement | null = $state(null);
	let scale = $state(1);
	let tx = $state(0);
	let ty = $state(0);
	let gesturing = $state(false);

	const MIN_SCALE = 1;
	const MAX_SCALE = 6;
	const TAP_SLOP = 8; // px of movement still counted as a tap, not a drag
	const DBL_MS = 250; // double-tap / -click window

	function resetZoom() {
		scale = 1;
		tx = 0;
		ty = 0;
	}

	// Reset the paged error and any zoom whenever the page or view mode changes.
	$effect(() => {
		page;
		config.viewMode;
		pageError = false;
		resetZoom();
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

	// Navigate by left/right half. Used directly by the non-zoomable modes; the
	// zoomable mode routes taps through here only when not zoomed in.
	function navByPoint(clientX: number, rect: DOMRect) {
		if (clientX < rect.left + rect.width / 2) goPrevPage();
		else goNextPage();
	}

	function onClickImage(e: MouseEvent): void {
		const ct = e.currentTarget as HTMLElement;
		if (!ct) return;
		navByPoint(e.clientX, ct.getBoundingClientRect());
	}

	// ----- Gesture helpers (contain mode) -----

	function clampPan() {
		if (!viewport || !comicTarget) return;
		const vw = viewport.clientWidth;
		const vh = viewport.clientHeight;
		const iw = comicTarget.clientWidth * scale;
		const ih = comicTarget.clientHeight * scale;
		const maxX = Math.max(0, (iw - vw) / 2);
		const maxY = Math.max(0, (ih - vh) / 2);
		tx = Math.min(maxX, Math.max(-maxX, tx));
		ty = Math.min(maxY, Math.max(-maxY, ty));
	}

	// Zoom by `ratio` keeping the screen point (fx, fy) anchored. The transform is
	// `translate(tx,ty) scale(scale)` about the stage centre, so a focal point f
	// maps as: tx' = r*tx + (1-r)*(f - centre).
	function zoomAt(fx: number, fy: number, ratio: number) {
		if (!viewport) return;
		const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * ratio));
		const r = ns / scale;
		if (r === 1) return;
		const rect = viewport.getBoundingClientRect();
		const cx = rect.left + rect.width / 2;
		const cy = rect.top + rect.height / 2;
		tx = r * tx + (1 - r) * (fx - cx);
		ty = r * ty + (1 - r) * (fy - cy);
		scale = ns;
		if (scale === 1) {
			tx = 0;
			ty = 0;
		} else {
			clampPan();
		}
	}

	const pointers = new Map<number, { x: number; y: number }>();
	let moved = 0;
	let lastDist = 0;
	let lastMid: { x: number; y: number } | null = null;
	let lastTapAt = 0;
	let pendingNav: ReturnType<typeof setTimeout> | null = null;

	function onPointerDown(e: PointerEvent) {
		// Leave right/middle mouse to the context menu.
		if (e.pointerType === 'mouse' && e.button !== 0) return;
		viewport?.setPointerCapture?.(e.pointerId);
		pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		gesturing = true;
		if (pointers.size === 1) {
			moved = 0;
		} else if (pointers.size === 2) {
			const [a, b] = [...pointers.values()];
			lastDist = Math.hypot(a.x - b.x, a.y - b.y);
			lastMid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
		}
	}

	function onPointerMove(e: PointerEvent) {
		const prev = pointers.get(e.pointerId);
		if (!prev) return;
		pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (pointers.size >= 2) {
			const [a, b] = [...pointers.values()];
			const dist = Math.hypot(a.x - b.x, a.y - b.y);
			const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
			if (lastDist > 0 && lastMid) {
				zoomAt(mid.x, mid.y, dist / lastDist);
				tx += mid.x - lastMid.x;
				ty += mid.y - lastMid.y;
				clampPan();
			}
			lastDist = dist;
			lastMid = mid;
		} else {
			const dx = e.clientX - prev.x;
			const dy = e.clientY - prev.y;
			moved += Math.hypot(dx, dy);
			if (scale > 1) {
				tx += dx;
				ty += dy;
				clampPan();
			}
		}
	}

	function onPointerUp(e: PointerEvent) {
		const wasTap = pointers.size === 1 && moved < TAP_SLOP;
		pointers.delete(e.pointerId);
		if (pointers.size < 2) {
			lastDist = 0;
			lastMid = null;
		}
		if (pointers.size === 0) gesturing = false;
		if (wasTap) handleTap(e.clientX, e.clientY);
	}

	function handleTap(x: number, y: number) {
		if (!viewport) return;
		const now = Date.now();
		if (now - lastTapAt < DBL_MS) {
			// Double tap / click: toggle between fit and 2.5x at the tap point.
			lastTapAt = 0;
			if (pendingNav) {
				clearTimeout(pendingNav);
				pendingNav = null;
			}
			if (scale > 1) resetZoom();
			else zoomAt(x, y, 2.5);
			return;
		}
		lastTapAt = now;
		if (scale > 1) return; // taps don't navigate while zoomed in
		// Defer navigation so a quick second tap can cancel it (double-tap zoom).
		const rect = viewport.getBoundingClientRect();
		pendingNav = setTimeout(() => {
			pendingNav = null;
			navByPoint(x, rect);
		}, DBL_MS);
	}

	function onWheel(e: WheelEvent) {
		e.preventDefault();
		zoomAt(e.clientX, e.clientY, Math.exp(-e.deltaY * 0.0015));
	}

	// Action wiring all gesture listeners; `wheel` needs passive:false to be able
	// to preventDefault the browser's page zoom.
	function gestures(node: HTMLElement) {
		node.addEventListener('pointerdown', onPointerDown);
		node.addEventListener('pointermove', onPointerMove);
		node.addEventListener('pointerup', onPointerUp);
		node.addEventListener('pointercancel', onPointerUp);
		node.addEventListener('wheel', onWheel, { passive: false });
		return {
			destroy() {
				node.removeEventListener('pointerdown', onPointerDown);
				node.removeEventListener('pointermove', onPointerMove);
				node.removeEventListener('pointerup', onPointerUp);
				node.removeEventListener('pointercancel', onPointerUp);
				node.removeEventListener('wheel', onWheel);
			}
		};
	}

	async function onLikePage() {
		const { error } = await ComicpageService.comicPageLike({ path: { id: file.id, page } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to like page' }));
		} else {
			addNotification(new SuccessNotification({ subtitle: 'Successfully liked page' }));
		}
	}

	// Single-image deletion is only meaningful for image albums (plain folders);
	// comic pages live inside an archive and aren't individually removable.
	const canDeletePage = $derived(file.type === MediaType.Image);
	let deletingPage = $state(false);
	async function onDeletePage() {
		if (deletingPage || !canDeletePage) return;
		deletingPage = true;
		const { data, error } = await ImagesService.imageDeletePage({
			path: { id: file.id, page }
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg ?? 'Failed to delete image' }));
		} else if (data) {
			// Reflect the new page count/cover on the shared instance and drop the
			// cached list so the album's page count isn't resurrected stale.
			file.update(data);
			refreshMediaFiles(MediaType.Image);
			if (maxPage <= 0) {
				// Album is now empty — nothing left to show.
				viewerState.onClose();
			} else {
				// Pages after the deleted one shifted down by one, so this slot now
				// holds the next image (or clamp to the new last page). Force the
				// <img> to refetch since the URL is unchanged but its bytes are not.
				page = Math.min(page, maxPage);
				loading = true;
				pageError = false;
				pageRetry += 1;
			}
			addNotification(new SuccessNotification({ subtitle: 'Deleted image' }));
		}
		deletingPage = false;
	}

	async function onSetCover() {
		const { error } = await ComicpageService.comicPageSetCover({ path: { id: file.id, page } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to set as cover' }));
		} else {
			// The backend rewrote the cover under the same filename. Bump the
			// version field so `coverUrl` changes and every <img> bound to it
			// re-fetches the new image (the server bumps the same field, so a later
			// reload from the API stays consistent).
			file.entityUpdateTime = new Date().toISOString();
			addNotification(new SuccessNotification({ subtitle: 'Successfully set as cover' }));
		}
	}
</script>

{#snippet pageBody()}
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
			style={`transform: translate3d(${tx}px, ${ty}px, 0) scale(${scale}); transition: ${gesturing ? 'none' : 'transform 0.12s ease-out'};`}
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
{/snippet}

<div class="viewer-root">
	<ProgressBar hideLabel max={maxPage} value={page} />
	{#if zoomable}
		<div class="fit-to-contain" class:zoomed={scale > 1} bind:this={viewport} use:gestures>
			{@render pageBody()}
		</div>
	{:else}
		<div class={viewClass} onclick={onClickImage} role="none">
			{@render pageBody()}
		</div>
	{/if}
	<ContextMenu target={targets}>
		<ContextMenuOption indented labelText="Like page" on:click={onLikePage} />
		<ContextMenuOption indented labelText="Set as Cover" on:click={onSetCover} />
		<ContextMenuDivider />
		<ContextMenuOption
			indented
			kind="danger"
			labelText="Delete"
			disabled={!canDeletePage || deletingPage}
			on:click={onDeletePage}
		/>
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
		overflow-x: auto;
	}
	.fit-to-height img {
		height: calc(100vh - 6rem);
	}

	/* Width mode (the mobile default): the page fills the viewport width and its
	   height follows the aspect ratio. Center it in the reading area so a page
	   shorter than the viewport isn't stranded against the top; min-height (not a
	   fixed height) lets a taller page grow the container and scroll normally. */
	.fit-to-width {
		max-width: 100vw;
		min-height: calc(100vh - 6rem);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.fit-to-width img {
		width: 100vw;
	}

	/* Contain mode: a fixed-height stage that centres the page both ways and
	   hosts the zoom/pan transform. */
	.fit-to-contain {
		height: calc(100vh - 6rem);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		touch-action: none;
	}
	.fit-to-contain.zoomed {
		cursor: grab;
	}
	.fit-to-contain img {
		max-height: 100%;
		max-width: 100%;
		width: auto;
		height: auto;
		transform-origin: center center;
		will-change: transform;
	}

	img {
		display: block;
		margin-left: auto;
		margin-right: auto;
		-webkit-user-drag: none;
	}
</style>
