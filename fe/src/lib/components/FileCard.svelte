<script lang="ts">
	import { Tag, Tile } from 'carbon-components-svelte';
	import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	interface Props {
		file: MediaFile;
		light?: boolean;
		onClickFile?: (file: MediaFile) => void;
		// Rows mixing media types label each card with its type instead of its size.
		showType?: boolean;
		// Draw a reading-progress bar along the bottom of the cover.
		showProgress?: boolean;
	}

	let {
		file,
		light = $bindable(false),
		onClickFile = () => undefined,
		showType = false,
		showProgress = false
	}: Props = $props();
	let comic = $derived(file as Comic);
	const typeLabel: Record<MediaType, string> = {
		[MediaType.Comic]: 'Comic',
		[MediaType.Video]: 'Video',
		[MediaType.Image]: 'Album'
	};
	function duration(seconds: number): string {
		const h = Math.floor(seconds / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		const s = String(seconds % 60).padStart(2, '0');
		return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
	}
</script>

<div class="card">
	<Tile bind:light on:click={() => onClickFile(file)}>
		<!-- size 0 means "not computed yet" (image folders skip it at scan time) -->
		{#if showType}
			<div class="left-top"><Tag type="cool-gray">{typeLabel[file.type]}</Tag></div>
		{:else if file.size > 0}
			<div class="left-top"><Tag>{file.size}MB</Tag></div>
		{/if}
		<div class="top-right">
			{#if file instanceof Video}
				{#if file.durationInSecond > 0}<Tag>{duration(file.durationInSecond)}</Tag>{/if}
			{:else if comic.viewed && comic.lastViewed === comic.page}
				<Tag type="green">{comic.page}p</Tag>
			{:else if comic.viewed}
				<Tag type="blue">{comic.lastViewed}/{comic.page}</Tag>
			{:else}
				<Tag>{comic.page}p</Tag>
			{/if}
		</div>
		<div class="imagecontainer">
			<img
				src={file.coverUrl}
				alt={`${file.id}`}
				loading="lazy"
				id={file.coverId}
				onerror={(e) => {
					const t = e.currentTarget as HTMLImageElement;
					t.style.display = 'none';
					t.parentElement?.classList.add('no-cover');
				}}
			/>
			{#if showProgress && comic.page > 0}
				<div class="progress" aria-hidden="true">
					<div style:width="{Math.min(100, (comic.lastViewed / comic.page) * 100)}%"></div>
				</div>
			{/if}
		</div>
		<div class="title">
			{file.name}
		</div>
	</Tile>
</div>

<style>
	:root {
		--card-width: 300px;
		--card-height: calc(var(--card-width) * 1.5);
		--font-height: 14px;
	}

	@media (max-width: 768px) {
		:root {
			--card-width: 48vw;
		}
	}

	.card {
		width: var(--card-width);
		height: var(--card-height);
		max-width: var(--card-width);
		max-height: var(--card-height);
		position: relative;
		overflow: hidden;
		/* In a horizontal scroller, cards keep their width instead of squeezing. */
		flex-shrink: 0;
		transition:
			transform 0.15s ease,
			box-shadow 0.15s ease;
	}

	.card .imagecontainer {
		position: relative;
		display: flex;
		width: 100%;
		height: calc(var(--card-height) - 3.5rem);
	}

	:global(.card .bx--tile) {
		padding: 0;
		height: 100%;
	}

	.title {
		padding: 0.5rem 0.5rem 0.25rem;
		font-size: 0.75rem;
		line-height: 1.25;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		color: var(--cds-text-01, #f4f4f4);
	}

	.progress {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 4px;
		background: rgba(0, 0, 0, 0.5);
	}

	.progress div {
		height: 100%;
		background: var(--cds-interactive-04, #4589ff);
	}

	.card img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	:global(.imagecontainer.no-cover) {
		background: var(--cds-ui-03, #393939);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	:global(.imagecontainer.no-cover::after) {
		content: '?';
		font-size: 3rem;
		color: var(--cds-text-03, #6f6f6f);
	}

	.card:hover {
		cursor: pointer;
		transform: translateY(-2px);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
	}

	.top-right {
		position: absolute;
		top: 0;
		right: 0;
		z-index: 1;
	}

	.left-top {
		position: absolute;
		top: 0;
		left: 0;
		z-index: 1;
	}
</style>
