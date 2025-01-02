<script lang="ts">
	import {
		Pagination,
		Search,
		Select,
		SelectItem,
		Button,
		Toggle
	} from 'carbon-components-svelte';
	import { Category, Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	import { Filter} from 'carbon-icons-svelte';

	import { slide } from 'svelte/transition';
	import FileCard from './FileCard.svelte';

	interface Props {
		searchStr?: string;
		files?: MediaFile[];
		onClickFile: (file: MediaFile) => void;
		onRefresh: () => void;
		category?: Category;
	}

	let {
		searchStr = $bindable(''),
		files = [],
		onClickFile,
		category = $bindable(Category.Home)
	}: Props = $props();
	let unreadOnly = $state(false);
	let curPage = $state(1);
	let pageSize = $state(20);
	let orderBy = $state('name');
	let showFilter = $state(false);
	let reverse = $state(false);
	let type = $derived(files[0]?.type);
	let searchFiles = $derived(files
		.filter((f) => (unreadOnly ? !f.viewed : true))
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
		}));
	let searchFilesR = $derived(reverse ? searchFiles.reverse() : searchFiles);
	let searchFilesInCurrentPage = $derived(searchFilesR.slice((curPage - 1) * pageSize, curPage * pageSize));

	// if searchStr change, reset page
	$effect(() => {
		searchStr;
		curPage = 1;
	});

	$effect(() => {
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
	});

	const onPaginationChange = (e: CustomEvent<{ page?: number; pageSize?: number }>) => {
		curPage = e.detail.page ?? curPage;
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
	page={curPage}
	{pageSize}
	on:change={onPaginationChange}
/>
{#if showFilter}
	<div transition:slide|global style="display: flex;gap:1rem; align-items:flex-end;">
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
		<FileCard {file} light={idx % 2 === 0} onClickFile={() => onClickFile(file)} />
	{/each}
</container>
<Pagination
	totalItems={searchFiles.length}
	pageSizes={[20, 25]}
	page={curPage}
	{pageSize}
	on:change={onPaginationChange}
/>
