<script lang="ts">
	import { goto, pushState } from '$app/navigation';
	import { page } from '$app/state';
	import { Search, SkeletonPlaceholder } from 'carbon-components-svelte';
	import FileCard from '$lib/components/FileCard.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import { MediaType, type MediaFile } from '$lib/model.svelte';
	import { includeAllKeywords } from '$lib/utility';

	let { data } = $props();

	let comics = $state([] as MediaFile[]);
	let videos = $state([] as MediaFile[]);
	let images = $state([] as MediaFile[]);
	let loaded = $state(false);
	$effect(() => {
		loaded = false;
		Promise.all([data.comics, data.videos, data.images])
			.then(([c, v, i]) => {
				comics = c;
				videos = v;
				images = i;
			})
			.finally(() => {
				loaded = true;
			});
	});

	// keep the query in the URL so the result is shareable and survives reloads
	let searchStr = $state('');
	$effect(() => {
		searchStr = page.url.searchParams.get('q') ?? '';
	});
	const runSearch = (q: string) => {
		goto(`/search?q=${encodeURIComponent(q.trim())}`);
	};

	// comics match on name, videos/images on path — same convention as the
	// per-type list pages.
	const filterFiles = (files: MediaFile[]) => {
		const keywords = searchStr.trim().toLowerCase().split(' ').filter(Boolean);
		if (keywords.length === 0) {
			return [] as MediaFile[];
		}
		return files.filter((f) =>
			includeAllKeywords((f.type === MediaType.Comic ? f.name : f.path).toLowerCase(), keywords)
		);
	};
	let comicResults = $derived(filterFiles(comics));
	let videoResults = $derived(filterFiles(videos));
	let imageResults = $derived(filterFiles(images));
	let totalResults = $derived(comicResults.length + videoResults.length + imageResults.length);

	let sections = $derived([
		{ title: 'Comics', files: comicResults },
		{ title: 'Videos', files: videoResults },
		{ title: 'Images', files: imageResults }
	]);

	let selectedFile: MediaFile | undefined = $state();
	const onClickFile = (file: MediaFile) => {
		selectedFile = file;
		pushState('', { showFileDetailModal: true });
	};
</script>

<div class="search-page">
	<div class="search-bar">
		<Search
			placeholder="Search across comics, videos and images..."
			bind:value={searchStr}
			on:blur={() => runSearch(searchStr)}
			on:keydown={(e) => {
				if (e.key === 'Enter') {
					runSearch(searchStr);
				}
			}}
		/>
	</div>

	{#if !loaded}
		<SkeletonPlaceholder style="width: 100%; height: 30vh" />
	{:else if !searchStr.trim()}
		<div class="empty-state">
			<p>Search everywhere</p>
			<p class="empty-hint">
				Type a keyword — an author, a title — to search all media types at once.
			</p>
		</div>
	{:else if totalResults === 0}
		<div class="empty-state">
			<p>No matches for "{searchStr}"</p>
			<p class="empty-hint">Try a different keyword.</p>
		</div>
	{:else}
		{#each sections as section}
			{#if section.files.length > 0}
				<section>
					<h3 class="section-title">
						{section.title} <span class="count">{section.files.length}</span>
					</h3>
					<div class="card-flexbox">
						{#each section.files as file, idx (`${file.type}-${file.id}`)}
							<div class="card-anim">
								<FileCard {file} light={idx % 2 === 0} onClickFile={() => onClickFile(file)} />
							</div>
						{/each}
					</div>
				</section>
			{/if}
		{/each}
	{/if}
</div>

{#if page.state.showFileDetailModal && selectedFile}
	<FileDetailModal
		open
		onCloseModal={() => history.back()}
		bind:file={selectedFile}
		onClickTag={(tag) => runSearch(tag)}
		onClickPrimaryButton={() => {
			if (selectedFile) {
				goto(`/${selectedFile.type}/${selectedFile.id}`);
			}
		}}
		onFileDeleted={(permenant = false) => {
			if (!selectedFile) {
				return;
			}
			if (permenant) {
				const lists = [comics, videos, images];
				for (const list of lists) {
					const idx = list.indexOf(selectedFile);
					if (idx >= 0) {
						list.splice(idx, 1);
						break;
					}
				}
			} else {
				selectedFile.archived = true;
			}
		}}
	/>
{/if}

<style>
	.search-page {
		padding: 0.5rem;
	}

	.search-bar {
		margin-bottom: 1rem;
	}

	.section-title {
		font-size: 1rem;
		margin: 1rem 0 0.5rem;
		color: var(--cds-text-01, #f4f4f4);
	}

	.count {
		font-size: 0.75rem;
		color: var(--cds-text-03, #8d8d8d);
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
		font-size: 0.875rem;
		margin-top: 0.5rem;
		color: var(--cds-text-03, #8d8d8d);
	}
</style>
