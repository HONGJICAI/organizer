<script lang="ts">
	import {
		ContentSwitcher,
		Pagination,
		Search,
		Switch,
		Tile,
		Select,
		SelectItem,
		Button,
		Toggle
	} from 'carbon-components-svelte';
	import { Category, Comic, MediaFile, MediaType, Video } from '$lib/model';
	import { Favorite, Filter, Home, RecentlyViewed, UpdateNow } from 'carbon-icons-svelte';
	import { config } from '$lib/config';
	import { includeAllKeywords } from '$lib/utility';
	import { slide } from 'svelte/transition';
	import FileCard from './FileCard.svelte';

	export let searchStr: string = '';
	export let files: MediaFile[] = [];
	export let onClickFile: (file: MediaFile) => void;
	export let onRefresh: () => void;
	export let category: Category = Category.Home;
	let unreadOnly = false;
	let page = 1;
	let pageSize = 20;
	let orderBy = 'name';
	let showFilter = false;
	let reverse = false;
	$: type = files[0]?.type;
	$: searchFiles = files
		.filter(
			(f) =>
				(unreadOnly ? !f.viewed : true) 
		)
		.sort((a, b) => {
			switch (orderBy) {
				case 'name':
					return a.name.localeCompare(b.name);
				case 'size':
					return a.size - b.size;
				case 'page':
					return ((a as Comic).page ?? 0) - ((b as Comic).page ?? 0);
				case 'duration':
					return ((a as Video).durationInSecond ?? 0) - ((b as Video).durationInSecond ?? 0);
				case 'date':
					return a.updateDate > b.updateDate ? 1 : -1;
				case 'path':
					return a.path.localeCompare(b.path);
				case 'id':
					return a.id - b.id;
				case 'random':
					return Math.random() - 0.5;
				case 'viewdate':
					return (a.lastViewedDate ?? 0) > (b.lastViewedDate ?? 0) ? 1 : -1;
			}
			return 0;
		});
	$: searchFilesR = reverse ? searchFiles.reverse() : searchFiles;
	$: searchFilesInCurrentPage = searchFilesR.slice(
		(page - 1) * pageSize,
		page * pageSize
	);

	// if searchStr change, reset page
	$: {
		searchStr;
		page = 1;
	}

	$: {
		category;
		switch (category) {
			case Category.Home:
			case Category.Favorite:
				orderBy = 'date';
				reverse = true;
				break;
			case Category.History:
			case Category.Archive:
				orderBy = 'viewdate';
				reverse = true;
				break;
		}
	}

	const onPaginationChange = (e: CustomEvent<{ page?: number; pageSize?: number }>) => {
		page = e.detail.page ?? page;
		pageSize = e.detail.pageSize ?? pageSize;
	};
</script>

<div style="display: flex;gap:1rem; align-items:flex-end;">
	<Search bind:value={searchStr} />
	<Select bind:selected={orderBy} labelText="Order By">
		{#if category == Category.Home || category == Category.Favorite}
			<SelectItem value="name" text="Name" />
			<SelectItem value="size" text="Size" />
			{#if type === MediaType.Comic}
				<SelectItem value="page" text="Page" />
			{/if}
			{#if type === MediaType.Video}
				<SelectItem value="duration" text="Duration" />
			{/if}
			<SelectItem value="date" text="Date" />
			<SelectItem value="path" text="Path" />
			<SelectItem value="id" text="ID" />
			<SelectItem value="random" text="Random" />
		{/if}
		{#if category == Category.History || category == Category.Archive}
			<SelectItem value="viewdate" text="ViewDate" />
		{/if}
	</Select>
	<Button
		icon={Filter}
		iconDescription="filter"
		kind="ghost"
		on:click={() => (showFilter = !showFilter)}
	/>
</div>
<Pagination
	totalItems={searchFiles.length}
	pageSizes={[20, 25]}
	{page}
	{pageSize}
	on:change={onPaginationChange}
/>
{#if showFilter}
	<div transition:slide style="display: flex;gap:1rem; align-items:flex-end;">
		<Toggle labelText="Unread Only" bind:toggled={unreadOnly} />
		<Select bind:selected={orderBy} labelText="Order By">
			<SelectItem value="name" text="Name" />
			<SelectItem value="size" text="Size" />
			{#if type === MediaType.Comic}
				<SelectItem value="page" text="Page" />
			{/if}
			{#if type === MediaType.Video}
				<SelectItem value="duration" text="Duration" />
			{/if}
			<SelectItem value="date" text="Date" />
			<SelectItem value="path" text="Path" />
			<SelectItem value="id" text="ID" />
			<SelectItem value="random" text="Random" />
		</Select>
		<Toggle labelText="Reverse Order" bind:toggled={reverse} />
	</div>
{/if}
<container style="display:flex;flex-wrap:wrap;justify-content:center;align-items:center">
	{#each searchFilesInCurrentPage as file, idx}
		<FileCard file={file} light={idx%2===0} onClickFile={() => onClickFile(file)} />
	{/each}
</container>
<Pagination
	totalItems={searchFiles.length}
	pageSizes={[20, 25]}
	{page}
	{pageSize}
	on:change={onPaginationChange}
/>
