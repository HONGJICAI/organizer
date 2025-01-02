<script lang="ts">
	import TagStack from '$lib/components/TagStack.svelte';
	import FileList from '$lib/components/FileList.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import { includeAllKeywords, separateFilename } from '$lib/utility';
	import { MediaType, type MediaFile, Comic, Category } from '$lib/model.svelte';
	import FileContent from '$lib/components/FileContent.svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import { ContentSwitcher, Switch, Button } from 'carbon-components-svelte';
	import { Home, Favorite, RecentlyViewed, UpdateNow, Recycle } from 'carbon-icons-svelte';
	import { page } from '$app/state';
	interface Props {
		data: any;
	}

	let { data }: Props = $props();
	let files = $state(data.files as MediaFile[]);
	let searchStr: string = $state(page.url.searchParams.get('q') ?? '');
	$effect(() => {
		const searchParams = new URLSearchParams(page.url.searchParams);
		const q = searchParams.get('q');
		if (q !== searchStr) {
			searchParams.set('q', searchStr);
			// goto(`?${searchParams.toString()}`);
		}
	});
	let showFileContent = $state(false);
	let showFileDetailModal = $state(false);
	let selectedFile: MediaFile | null = $state(null);

	const genTagMap = (names: string[]) => {
		let tag2count: Map<string, number> = new Map<string, number>();
		names.forEach((n) => {
			const tags = separateFilename(n);
			for (const tag of tags) {
				if (tag2count.has(tag)) {
					tag2count.set(tag, tag2count.get(tag)! + 1);
				} else {
					tag2count.set(tag, 1);
				}
			}
		});
		return tag2count;
	};

	async function onClickTag(tag: string) {
		searchStr = tag;
	}

	const onClickFile = (file: MediaFile) => {
		selectedFile = file;
		showFileDetailModal = true;
	};
	const onRefresh = () => {
		invalidateAll();
	};
	let viewContentIdx: Category = $state(Category.Home);
	let viewContentIdx2filterfunc = {
		// home
		0: (f: MediaFile) => {
			return !f.archive;
		},
		// favorite
		1: (f: MediaFile) => {
			return f.like;
		},
		// recently viewed
		2: (f: MediaFile) => {
			return !f.archive && f.viewed;
		},
		// archive
		3: (f: MediaFile) => {
			return f.archive;
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

<container id={showFileContent ? 'hidelist' : null}>
	<div id="left">
		<TagStack tag2countMap={filteredTagMap} {onClickTag} title="All Tags" />
		{#if searchStr}
			<TagStack tag2countMap={searchedTagMap} {onClickTag} title="Searched Tags" />
		{/if}
	</div>
	<div id="right">
		<container style="display:flex; justify-content:space-between">
			<div>
				<ContentSwitcher bind:selectedIndex={viewContentIdx}>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Home style="margin-right: 0.5rem;" />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Favorite style="margin-right: 0.5rem;" />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<RecentlyViewed style="margin-right: 0.5rem;" />
						</div>
					</Switch>
					<Switch>
						<div style="display: flex; align-items: center;">
							<Recycle style="margin-right: 0.5rem;" />
						</div>
					</Switch>
				</ContentSwitcher>
			</div>
			<Button iconDescription="refresh" icon={UpdateNow} on:click={() => onRefresh()} />
		</container>
		<FileList
			files={searchFiles}
			bind:searchStr
			{onClickFile}
			{onRefresh}
			bind:category={viewContentIdx}
		/>
	</div>

	{#if showFileDetailModal && selectedFile}
		<FileDetailModal
			open={showFileDetailModal}
			onCloseModal={() => {
				showFileDetailModal = false;
			}}
			bind:file={selectedFile}
			onClickTag={(tag) => {
				searchStr = tag;
				showFileDetailModal = false;
			}}
			onClickPrimaryButton={() => {
				showFileDetailModal = false;
				showFileContent = true;
			}}
			onFileDeleted={(permenant = false) => {
				if (!selectedFile) {
					return;
				}
				if (permenant) {
					files.splice(files.indexOf(selectedFile), 1);
				} else {
					selectedFile.archive = true;
				}
			}}
		/>
	{/if}
</container>
{#if showFileContent && selectedFile}
	<FileContent
		file={selectedFile}
		onClose={() => ((showFileContent = false), (showFileDetailModal = true))}
	/>
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
		gap: 1rem;
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
