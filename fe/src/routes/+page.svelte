<script lang="ts">
	import FileCard from '$lib/components/FileCard.svelte';
	import HorizontalScroller from '$lib/components/HorizontalScroller.svelte';
	import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	import { SkeletonPlaceholder } from 'carbon-components-svelte';
	import { Book, Image, MediaLibrary } from 'carbon-icons-svelte';
	import { goto } from '$app/navigation';

	let { data } = $props();
</script>

<div class="home">
	<section class="media-section">
		<a class="section-heading" href="/comic">
			<Book size={20} />
			<span>Comics</span>
		</a>
		<HorizontalScroller>
			{#await data.comics}
				{#each { length: 5 } as _}
					<SkeletonPlaceholder style="width: 300px; height: 450px; flex-shrink: 0;" />
				{/each}
			{:then comics}
				{#each comics.data ?? [] as file}
					<FileCard file={new Comic(file)} onClickFile={(f) => goto(`/comic/${f.id}`)} />
				{/each}
			{:catch error}
				<div class="error">{error}</div>
			{/await}
		</HorizontalScroller>
	</section>

	<section class="media-section">
		<a class="section-heading" href="/video">
			<MediaLibrary size={20} />
			<span>Videos</span>
		</a>
		<HorizontalScroller>
			{#await data.videos}
				{#each { length: 5 } as _}
					<SkeletonPlaceholder style="width: 300px; height: 450px; flex-shrink: 0;" />
				{/each}
			{:then videos}
				{#each videos.data ?? [] as file}
					<FileCard file={new Video(file)} onClickFile={(f) => goto(`/video/${f.id}`)} />
				{/each}
			{:catch error}
				<div class="error">{error}</div>
			{/await}
		</HorizontalScroller>
	</section>

	<section class="media-section">
		<a class="section-heading" href="/image">
			<Image size={20} />
			<span>Images</span>
		</a>
		<HorizontalScroller>
			{#await data.images}
				{#each { length: 5 } as _}
					<SkeletonPlaceholder style="width: 300px; height: 450px; flex-shrink: 0;" />
				{/each}
			{:then images}
				{#each images.data ?? [] as file}
					<FileCard
						file={new MediaFile(MediaType.Image, file)}
						onClickFile={(f) => goto(`/image/${f.id}`)}
					/>
				{/each}
			{:catch error}
				<div class="error">{error}</div>
			{/await}
		</HorizontalScroller>
	</section>
</div>

<style>
	.home {
		padding: 1rem 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 2rem;
	}

	@media (max-width: 768px) {
		.home {
			padding: 0.75rem;
			gap: 1.25rem;
		}
		.section-heading {
			font-size: 1rem;
		}
	}

	.media-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.section-heading {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--cds-text-01, #f4f4f4);
		text-decoration: none;
	}

	.section-heading:hover {
		color: var(--cds-link-01, #78a9ff);
	}

	.error {
		color: var(--cds-text-error, #ff8389);
		padding: 1rem;
	}
</style>
