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
	import { slide, scale } from 'svelte/transition';
	import { flip } from 'svelte/animate';
	import FileCard from '$lib/components/FileCard.svelte';
	import { getOrderByOptions } from './orderByOptions.js';

	let { data } = $props();
	let dataLoaded = $state(false);
	let files = $state([] as MediaFile[]);
	$effect(() => {
		const pending = data.files;
		// reset immediately so a slow/failed load never shows the previous
		// media type's content while switching between comic/video/image
		dataLoaded = false;
		files = [];
		let cancelled = false;
		pending
			?.then((f) => {
				if (!cancelled) files = f;
			})
			.catch(() => {
				if (!cancelled) files = [];
			})
			.finally(() => {
				if (!cancelled) dataLoaded = true;
			});
		return () => {
			cancelled = true;
		};
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

<div class="layout" id={page.state.showFileContent ? 'hidelist' : null}>
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
		<div class="top-bar">
			<ContentSwitcher selectedIndex={category} on:change={onCategoryChange}>
				<Switch>
					<div class="switch-label"><Home size={16} /><span>Home</span></div>
				</Switch>
				<Switch>
					<div class="switch-label"><Favorite size={16} /><span>Favorites</span></div>
				</Switch>
				<Switch>
					<div class="switch-label"><RecentlyViewed size={16} /><span>Recent</span></div>
				</Switch>
				<Switch>
					<div class="switch-label"><Recycle size={16} /><span>Archive</span></div>
				</Switch>
			</ContentSwitcher>
			<Button
				iconDescription="refresh"
				icon={UpdateNow}
				on:click={onRefresh}
				disabled={!dataLoaded}
			/>
		</div>
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
				<div class="card-flexbox">
					{#if searchFilesInCurrentPage.length === 0}
						<div class="empty-state">
							{#if searchStr}
								<p>No files match your search</p>
								<p class="empty-hint">Try a different search term or clear the filter.</p>
							{:else}
								<p>Nothing found here</p>
								<p class="empty-hint">There are no items in this view yet.</p>
							{/if}
						</div>
					{:else}
						{#each searchFilesInCurrentPage as file, idx (file.id)}
							<div
								class="card-anim"
								animate:flip={{ duration: 250 }}
								in:scale={{ duration: 200, start: 0.9 }}
								out:scale={{ duration: 150, start: 0.85 }}
							>
								<FileCard {file} light={idx % 2 === 0} onClickFile={() => onClickFile(file)} />
							</div>
						{/each}
					{/if}
				</div>
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
</div>
{#if page.state.showFileContent && selectedFile}
	<FileContent file={selectedFile} onClose={() => history.back()} />
{/if}

<style>
	.layout {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		align-items: flex-start;
		gap: 0.5rem;
	}

	#hidelist {
		display: none;
	}

	#left {
		min-width: 200px;
		max-width: 260px;
		flex-shrink: 0;
	}
	#right {
		flex: 1;
		min-width: 0;
	}

	@media screen and (max-width: 800px) {
		#left {
			width: 100%;
			min-width: 0;
			max-width: 100%;
		}
		#right {
			width: 100%;
		}
		.top-bar {
			flex-wrap: wrap;
			gap: 0.5rem;
		}
		.switch-label span {
			display: none;
		}
		.search-bar {
			gap: 0.5rem;
		}
	}

	.top-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		overflow: hidden;
		margin-bottom: 0.25rem;
	}

	.switch-label {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
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
		justify-content: flex-start;
		align-items: flex-start;
		gap: 0.5rem;
		padding: 0.5rem 0;
	}

	.card-anim {
		width: var(--card-width);
	}

	.empty-state {
		width: 100%;
		padding: 3rem 1rem;
		text-align: center;
		color: var(--cds-text-02, #c6c6c6);
	}

	.empty-state p {
		font-size: 1.125rem;
		margin: 0;
	}

	.empty-hint {
		font-size: 0.875rem !important;
		margin-top: 0.5rem !important;
		color: var(--cds-text-03, #8d8d8d) !important;
	}
</style>
