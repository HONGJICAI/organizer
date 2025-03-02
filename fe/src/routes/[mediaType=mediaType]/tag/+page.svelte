<script lang="ts">
	import { goto } from '$app/navigation';
	import type { MediaFile } from '$lib/model.svelte';
	import { Loading, Tag } from 'carbon-components-svelte';

	let { data } = $props();
	let files = $state([] as MediaFile[]);
	$effect(() => {
		data.files?.then((f) => {
			files = f;
		});
	});
	interface TagDetail {
		tag: string;
		count: number;
		archiveCount: number;
		favoriteCount: number;
		viewCount: number;
	}
	const genTagDetail = (files: MediaFile[]) => {
		const tag2detail = new Map<string, TagDetail>();
		files.forEach((f) => {
			f.tags.forEach((tag) => {
				const tagDetail = tag2detail.get(tag) ?? {
					tag,
					count: 0,
					archiveCount: 0,
					favoriteCount: 0,
					viewCount: 0
				};
				tagDetail.count++;
				if (f.archived) {
					tagDetail.archiveCount++;
				}
				if (f.favorited) {
					tagDetail.favoriteCount++;
				}
				if (f.viewed) {
					tagDetail.viewCount++;
				}
				tag2detail.set(tag, tagDetail);
			});
		});
		// remove tag count less than 3
		for (const [tag, detail] of tag2detail) {
			if (detail.count < 3) {
				tag2detail.delete(tag);
			}
		}
		return tag2detail;
	};
	let tagDetail = $derived(genTagDetail(files));
	let topArchiveRateTagDetail = $derived(
		Array.from(tagDetail.values())
			.sort((a, b) => b.archiveCount / b.count - a.archiveCount / a.count)
			.slice(0, 20)
	);
	let topViewRateTagDetail = $derived(
		Array.from(tagDetail.values())
			.sort((a, b) => b.viewCount / b.count - a.viewCount / a.count)
			.slice(0, 20)
	);
	let topFavoriteRateTagDetail = $derived(
		Array.from(tagDetail.values())
			.sort((a, b) => b.favoriteCount / b.count - a.favoriteCount / a.count)
			.slice(0, 20)
	);
	const onTagClick = (tag: string) => {
		goto(`/${data.mediaType}?q=${tag}`);
	};
</script>

{#await data.files}
	<Loading />
{:then}
	<h2>Most view rate tag</h2>
	<div>
		{#each topViewRateTagDetail as tag}
			<Tag on:click={() => onTagClick(tag.tag)}>{tag.tag}</Tag>{tag.viewCount}/{tag.count}
		{/each}
	</div>
	<h2>Most archive rate tag</h2>
	<div>
		{#each topArchiveRateTagDetail as tag}
			<Tag on:click={() => onTagClick(tag.tag)}>{tag.tag}</Tag>{tag.archiveCount}/{tag.count}
		{/each}
	</div>
	<h2>Most favorite rate tag</h2>
	<div>
		{#each topFavoriteRateTagDetail as tag}
			<Tag on:click={() => onTagClick(tag.tag)}>{tag.tag}</Tag>{tag.favoriteCount}/{tag.count}
		{/each}
	</div>
{:catch error}
	<div>{error}</div>
{/await}
