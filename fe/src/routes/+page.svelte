<script lang="ts">
	import FileCard from '$lib/components/FileCard.svelte';
	import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	import { Accordion, Link, SkeletonPlaceholder } from 'carbon-components-svelte';
	import { Book, Image, MediaLibrary } from 'carbon-icons-svelte';

	let { data } = $props();
</script>

<Accordion>
	<Link href="/comic" size="lg" icon={Book}>Comics homepage</Link>
	<br />
	<div class="card-container">
		{#await data.comics}
			<SkeletonPlaceholder style="width: 100%" />
		{:then data}
			{#each data.data! as file}
				<div class="card">
					<FileCard file={new Comic(file)} onClickFile={(file) => console.log(file)} />
				</div>
			{/each}
		{:catch error}
			<div>{error}</div>
		{/await}
	</div>
	<Link href="/video" size="lg" icon={MediaLibrary}>Videos homepage</Link>
	<br />
	<div class="card-container">
		{#await data.videos}
			<SkeletonPlaceholder style="width: 100%" />
		{:then data}
			{#each data.data! as file}
				<div class="card">
					<FileCard file={new Video(file)} onClickFile={(file) => console.log(file)} />
				</div>
			{/each}
		{:catch error}
			<div>{error}</div>
		{/await}
	</div>
	<Link href="/image" size="lg" icon={Image}>Images homepage</Link>
	<br />
	<div class="card-container">
		{#await data.images}
			<SkeletonPlaceholder style="width: 100%" />
		{:then data}
			{#each data.data! as file}
				<div class="card">
					<FileCard
						file={new MediaFile(MediaType.Image, file)}
						onClickFile={(file) => console.log(file)}
					/>
				</div>
			{/each}
		{:catch error}
			<div>{error}</div>
		{/await}
	</div>
</Accordion>

<style>
	.card-container {
		display: flex;
		min-height: 300px;
		/* can scroll to right inside this */
		overflow-x: visible;
		overflow-y: hidden;
		/* beauty scroll bar */
		scrollbar-width: thin;
		scrollbar-color: #888 #f1f1f1;
	}
	.card {
		/* max-width: 25%; */
	}

	.card:hover {
		/* z-index: 1; */
	}
</style>
