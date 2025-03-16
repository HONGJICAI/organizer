<script lang="ts">
	import TagStack from '$lib/components/TagStack.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import { genTagMap, includeAllKeywords } from '$lib/utility';
	import {
		MediaType,
		Category,
		MediaFile,
		type MediaFileComparisonType,
		MediaFileComparison
	} from '$lib/model.svelte';
	import FileContent from '$lib/components/FileContent.svelte';
	import { goto, invalidateAll, pushState } from '$app/navigation';
	import {
		ContentSwitcher,
		Switch,
		Button,
		SkeletonPlaceholder,
		Search,
		Select,
		SelectItem,
		Toggle
	} from 'carbon-components-svelte';
	import { Home, Favorite, RecentlyViewed, UpdateNow, Recycle, Filter } from 'carbon-icons-svelte';
	import { page } from '$app/state';
	import { config } from '$lib/config.svelte.js';
	import PaginationContainer from '$lib/components/PaginationContainer.svelte';
	import { slide } from 'svelte/transition';
	import FileCard from '$lib/components/FileCard.svelte';
	import { getOrderByOptions } from './orderByOptions.js';

	let { data } = $props();
	let dataLoaded = $state(false);
	let files = $state([] as MediaFile[]);
	$effect(() => {
		dataLoaded = false;
		data.files
			?.then((f) => {
				files = f;
			})
			.finally(() => {
				dataLoaded = true;
			});
	});
	let searchStr: string = $state('');
	let curPage = $state(1);
	let category = $state(Category.Home);
	let selectedFile: MediaFile | undefined = $state();
	let pageSize = $state(20);
	let unreadOnly = $state(false);
	let orderBy = $state<MediaFileComparisonType>(MediaFileComparison.UpdatedDate);
	let reverse = $state(true);
	let showFilter = $state(config.DeviceType === 'Desktop');
	// sync url state
	$effect(() => {
		searchStr = page.url.searchParams.get('q') ?? '';
		const p = page.url.searchParams.get('p');
		curPage = p ? parseInt(p) : 1;
		const c = page.url.searchParams.get('c');
		category = c ? parseInt(c) : Category.Home;
	});

	const syncStateToUrl = () => {
		goto(`?q=${searchStr}&p=${curPage}&c=${category}`);
	};

	async function onClickTag(tag: string) {
		searchStr = tag;
		curPage = 1;
		syncStateToUrl();
	}

	const onClickFile = (file: MediaFile) => {
		selectedFile = file;
		pushState('', {
			showFileDetailModal: true
		});
	};
	const onSearchBlur = (search: string) => {
		searchStr = search;
		curPage = 1;
		syncStateToUrl();
	};
	const onPageChange = (page: number) => {
		curPage = page;
		syncStateToUrl();
	};
	const onRefresh = () => {
		invalidateAll();
	};
	const onCategoryChange = (e: CustomEvent<number>) => {
		category = e.detail;
		curPage = 1;
		syncStateToUrl();
	};
	const onPaginationChange = (newpage?: number, newpageSize?: number) => {
		if (newpage && newpage !== curPage) {
			onPageChange?.(newpage);
		}
		curPage = newpage ?? curPage;
		pageSize = newpageSize ?? pageSize;
	};
	let category2filterfunc = {
		// home
		0: (f: MediaFile) => {
			return !f.archived;
		},
		// favorite
		1: (f: MediaFile) => {
			return f.favorited;
		},
		// recently viewed
		2: (f: MediaFile) => {
			return !f.archived && f.viewed;
		},
		// archive
		3: (f: MediaFile) => {
			return f.archived;
		}
	};
	let categoryFiles = $derived(files.filter(category2filterfunc[category]));
	let searchFiles = $derived(
		categoryFiles.filter((f) =>
			includeAllKeywords(
				(f.type === MediaType.Comic ? f.name : f.path).toLowerCase(),
				searchStr.trim().toLowerCase().split(' ')
			)
		)
	);
	let mediaType = $derived(files[0]?.type);
	let filteredTagMap = $derived(
		genTagMap(categoryFiles.map((c) => (mediaType === MediaType.Comic ? c.name : c.path)))
	);
	let searchedTagMap = $derived(
		genTagMap(searchFiles.map((c) => (mediaType === MediaType.Comic ? c.name : c.path)))
	);

	const orderByOptions = $derived.by(() => {
		switch (category) {
			case Category.Home:
			case Category.Favorite:
				return getOrderByOptions(mediaType);
			case Category.History:
			case Category.Archive:
				return [{ value: MediaFileComparison.ViewedDate, text: 'ViewDate' }];
		}
	});
	let searchFilesInCurrentPage = $derived(
		(category === Category.Home && unreadOnly ? searchFiles.filter((f) => !f.viewed) : searchFiles)
			.sort((a, b) => (reverse ? -a.compareTo(b, orderBy) : a.compareTo(b, orderBy)))
			.slice((curPage - 1) * pageSize, curPage * pageSize)
	);
</script>

<container id={page.state.showFileContent ? 'hidelist' : null}>
	<div id="left">
		{#if !dataLoaded}
			<TagStack skeleton title="All Tags" />
		{:else}
			<TagStack tag2countMap={filteredTagMap} {onClickTag} title="All Tags" />
			{#if searchStr}
				<TagStack tag2countMap={searchedTagMap} {onClickTag} title="Searched Tags" />
			{/if}
		{/if}
	</div>
	<div id="right">
		<container style="display:flex; justify-content:space-between; overflow: hidden;">
			<div>
				<ContentSwitcher selectedIndex={category} on:change={onCategoryChange}>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Home />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Favorite />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<RecentlyViewed />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Recycle />
						</div>
					</Switch>
				</ContentSwitcher>
			</div>
			<Button
				iconDescription="refresh"
				icon={UpdateNow}
				on:click={onRefresh}
				disabled={!dataLoaded}
			/>
		</container>
		<div class="search-bar">
			<Search bind:value={searchStr} on:blur={() => onSearchBlur(searchStr)} />
			{#if config.OrderByPosition === 'NextToSearchBar' && orderByOptions}
				<Select bind:selected={orderBy} labelText="Order By">
					{#each orderByOptions as { value, text }}
						<SelectItem {value} {text} />
					{/each}
				</Select>
			{/if}
			<Button
				icon={Filter}
				iconDescription="filter"
				kind="ghost"
				on:click={() => (showFilter = !showFilter)}
			/>
		</div>
		{#if !dataLoaded}
			<PaginationContainer skeleton>
				<SkeletonPlaceholder style="width: 100%; height: 30vh" />
			</PaginationContainer>
		{:else}
			<PaginationContainer
				totalItems={searchFiles.length}
				page={searchFilesInCurrentPage.length > 0 ? curPage : undefined}
				{pageSize}
				{onPaginationChange}
			>
				{#if showFilter}
					<div transition:slide style="display: flex;gap:1rem; align-items:flex-end;">
						{#if category === Category.Home}
							<Toggle labelText="Unread Only" bind:toggled={unreadOnly} />
						{/if}
						{#if config.OrderByPosition === 'InFilterPanel' && orderByOptions}
							<Select bind:selected={orderBy} labelText="Order By">
								{#each orderByOptions as { value, text }}
									<SelectItem {value} {text} />
								{/each}
							</Select>
						{/if}
						<Toggle labelText="Reverse Order" bind:toggled={reverse} />
					</div>
				{/if}
				<container class="card-flexbox">
					{#if searchFilesInCurrentPage.length === 0}
						<div style="width: 100%; text-align: center; font-size: 1.5rem; color: var(--text-01);">
							No Files Found
						</div>
					{:else}
						{#each searchFilesInCurrentPage as file, idx}
							<FileCard {file} light={idx % 2 === 0} onClickFile={() => onClickFile(file)} />
						{/each}
					{/if}
				</container>
			</PaginationContainer>
		{/if}
	</div>

	{#if page.state.showFileDetailModal && selectedFile}
		<FileDetailModal
			open
			onCloseModal={() => {
				history.back();
			}}
			bind:file={selectedFile}
			{onClickTag}
			onClickPrimaryButton={() => {
				pushState('', {
					showFileDetailModal: false,
					showFileContent: true
				});
			}}
			onFileDeleted={(permenant = false) => {
				if (!selectedFile) {
					return;
				}
				if (permenant) {
					files.splice(files.indexOf(selectedFile), 1);
				} else {
					selectedFile.archived = true;
				}
			}}
		/>
	{/if}
</container>
{#if page.state.showFileContent && selectedFile}
	<FileContent file={selectedFile} onClose={() => history.back()} />
{/if}

<style>
	container {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		align-items: flex-start;
	}

	#hidelist {
		display: none;
	}

	#left {
		width: 20%;
	}
	#right {
		width: 80%;
	}

	@media screen and (max-width: 800px) {
		#left {
			width: 100%;
		}
		#right {
			width: 100%;
		}
	}
	.search-bar {
		display: flex;
		gap: 1rem;
		align-items: flex-end;
		overflow: hidden;
	}

	.card-flexbox {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		align-items: center;
	}
</style>
