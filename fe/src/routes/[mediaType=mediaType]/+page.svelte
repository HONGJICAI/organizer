<script lang="ts">
	import TagStack from '$lib/components/TagStack.svelte';
	import FileList from '$lib/components/FileList.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import { genTagMap, includeAllKeywords } from '$lib/utility';
	import { MediaType, type MediaFile, Category } from '$lib/model.svelte';
	import FileContent from '$lib/components/FileContent.svelte';
	import { goto, invalidateAll, pushState } from '$app/navigation';
	import { ContentSwitcher, Switch, Button, SkeletonPlaceholder } from 'carbon-components-svelte';
	import { Home, Favorite, RecentlyViewed, UpdateNow, Recycle } from 'carbon-icons-svelte';
	import { page } from '$app/state';

	let { data } = $props();
	let files = $state([] as MediaFile[]);
	$effect(() => {
		data.files?.then((f) => {
			files = f;
		});
	});
	let searchStr: string = $state('');
	$effect(() => {
		const q = page.url.searchParams.get('q');
		if (q) {
			searchStr = q;
		} else {
			searchStr = '';
		}
	});
	let selectedFile: MediaFile | undefined = $state();

	async function onClickTag(tag: string) {
		goto(`?q=${tag}`);
	}

	const onClickFile = (file: MediaFile) => {
		selectedFile = file;
		pushState('', {
			showFileDetailModal: true
		});
	};
	const onSearchBlur = (search: string) => {
		goto(`?q=${search}`);
	};
	const onRefresh = () => {
		invalidateAll();
	};
	let viewContentIdx: Category = $state(Category.Home);
	let viewContentIdx2filterfunc = {
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
	let filteredFiles = $derived(files.filter(viewContentIdx2filterfunc[viewContentIdx]));
	let searchFiles = $derived.by(() =>
		filteredFiles.filter((f) =>
			includeAllKeywords(
				(f.type === MediaType.Comic ? f.name : f.path).toLowerCase(),
				searchStr.trim().toLowerCase().split(' ')
			)
		)
	);
	let mediaType = $derived(files[0]?.type);
	let filteredTagMap = $derived(
		genTagMap(filteredFiles.map((c) => (mediaType === MediaType.Comic ? c.name : c.path)))
	);
	let searchedTagMap = $derived(
		genTagMap(searchFiles.map((c) => (mediaType === MediaType.Comic ? c.name : c.path)))
	);
</script>

<container id={page.state.showFileContent ? 'hidelist' : null}>
	<div id="left">
		{#await data.files}
			<TagStack skeleton={true} title="All Tags" />
		{:then files}
			<TagStack tag2countMap={filteredTagMap} {onClickTag} title="All Tags" />
			{#if searchStr}
				<TagStack tag2countMap={searchedTagMap} {onClickTag} title="Searched Tags" />
			{/if}
		{/await}
	</div>
	<div id="right">
		<container style="display:flex; justify-content:space-between; overflow: hidden;">
			<div>
				<ContentSwitcher bind:selectedIndex={viewContentIdx}>
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
			{#await data.files then files}
				<Button iconDescription="refresh" icon={UpdateNow} on:click={() => onRefresh()} />
			{/await}
		</container>
		{#await data.files}
			<SkeletonPlaceholder style="width: 100%; height: 80vh" />
		{:then files}
			<FileList
				files={searchFiles}
				bind:searchStr
				{onClickFile}
				{onRefresh}
				{onSearchBlur}
				bind:category={viewContentIdx}
			/>
		{/await}
	</div>

	{#if page.state.showFileDetailModal && selectedFile}
		<FileDetailModal
			open={true}
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
</style>
