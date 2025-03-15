<script lang="ts">
	import FileCard from '$lib/components/FileCard.svelte';
	import HorizontalScroller from '$lib/components/HorizontalScroller.svelte';
	import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	import { Accordion, Link, SkeletonPlaceholder } from 'carbon-components-svelte';
	import { Book, Image, MediaLibrary } from 'carbon-icons-svelte';

	let { data } = $props();
</script>

<Accordion>
	<Link href="/comic" size="lg" icon={Book}>Comics homepage</Link>
	<br />
	<HorizontalScroller>
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
	</HorizontalScroller>
	<Link href="/video" size="lg" icon={MediaLibrary}>Videos homepage</Link>
	<br />
	<HorizontalScroller>
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
		{/await}</HorizontalScroller
	>
	<Link href="/image" size="lg" icon={Image}>Images homepage</Link>
	<br />
	<HorizontalScroller>
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
		{/await}</HorizontalScroller
	>
</Accordion>

<style>
</style>
