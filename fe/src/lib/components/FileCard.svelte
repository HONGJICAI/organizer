<script lang="ts">
	import { Tag, Tile } from 'carbon-components-svelte';
	import { Comic, MediaFile, MediaType } from '$lib/model.svelte';
	interface Props {
		file: MediaFile;
		light?: boolean;
		onClickFile: (file: MediaFile) => void;
	}

	let { file, light = $bindable(false), onClickFile }: Props = $props();
	let comic = $derived(file as Comic);
</script>

<div class="card">
	<Tile bind:light on:click={() => onClickFile(file)}>
		<div class="left-top"><Tag>{file.size}MB</Tag></div>
		<div class="top-right">
			{#if comic.viewed && comic.lastViewed === comic.page}
				<Tag type="green">{comic.page}p</Tag>
			{:else if comic.viewed}
				<Tag type="blue">{comic.lastViewed}/{comic.page}</Tag>
			{:else}
				<Tag>{comic.page}p</Tag>
			{/if}
		</div>
		<div class="imagecontainer">
			<img src={file.coverUrl} alt={`${file.id}`} id={file.coverId} />
		</div>
		{file.name}
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
	}

	.card .imagecontainer {
		display: flex;
		padding-left: 1;
		padding-right: 1;
		width: 100%;
		height: calc(var(--card-height) - 3 * var(--font-height));
	}

	.card img {
		width: 100%;
		object-fit: contain;
	}

	.card:hover {
		cursor: pointer;
	}

	.top-right {
		position: absolute;
		top: 0;
		right: 0;
	}

	.top-middle {
		position: absolute;
		top: 0;
		left: 50%;
		transform: translateX(-50%);
	}

	.left-top {
		position: absolute;
		top: 0;
		left: 0;
	}
</style>
