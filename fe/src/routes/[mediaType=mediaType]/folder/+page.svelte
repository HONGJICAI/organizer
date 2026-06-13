<script lang="ts">
	import {
		Breadcrumb,
		BreadcrumbItem,
		SkeletonPlaceholder,
		Tile,
		Toggle
	} from 'carbon-components-svelte';
	import { Folder, Home } from 'carbon-icons-svelte';
	import { goto, pushState } from '$app/navigation';
	import { page } from '$app/state';
	import { MediaFile } from '$lib/model.svelte';
	import { buildFolderTree, findNode, collectFiles, nodeKey } from '$lib/folderTree';
	import FileCard from '$lib/components/FileCard.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import FileContent from '$lib/components/FileContent.svelte';
	import PaginationContainer from '$lib/components/PaginationContainer.svelte';

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

	let mediaType = $derived(page.params.mediaType);
	let includeSub = $state(false);
	let pageSize = $state(20);
	let selectedFile: MediaFile | undefined = $state();

	// archived files belong to the Archive view, not the folder browser
	let visibleFiles = $derived(files.filter((f) => !f.archived));
	let tree = $derived(buildFolderTree(visibleFiles));

	// current directory + page live in the URL so the back button works
	let dir = $derived(page.url.searchParams.get('dir') ?? '');
	let curPage = $derived(parseInt(page.url.searchParams.get('p') ?? '1') || 1);
	let currentNode = $derived(findNode(tree, dir) ?? tree);

	let crumbs = $derived(
		currentNode.segments.map((seg, i) => ({
			name: seg,
			key: currentNode.segments.slice(0, i + 1).join('/')
		}))
	);
	let subfolders = $derived(includeSub ? [] : currentNode.children);
	let displayFiles = $derived(
		(includeSub ? collectFiles(currentNode) : currentNode.files)
			.slice()
			.sort((a, b) => a.name.localeCompare(b.name))
	);
	let filesInPage = $derived(displayFiles.slice((curPage - 1) * pageSize, curPage * pageSize));

	const goToDir = (key: string) => {
		goto(`?dir=${encodeURIComponent(key)}`);
	};
	const onPaginationChange = (newPage?: number, newPageSize?: number) => {
		pageSize = newPageSize ?? pageSize;
		if (newPage && newPage !== curPage) {
			goto(`?dir=${encodeURIComponent(dir)}&p=${newPage}`);
		}
	};
	const onClickFile = (file: MediaFile) => {
		selectedFile = file;
		pushState('', { showFileDetailModal: true });
	};
</script>

<div class="layout" id={page.state.showFileContent ? 'hidelist' : null}>
	<div class="header-bar">
		<Breadcrumb noTrailingSlash>
			<BreadcrumbItem>
				<button class="crumb" onclick={() => goToDir('')}>
					<Home size={16} /><span>{mediaType}</span>
				</button>
			</BreadcrumbItem>
			{#each crumbs as crumb, i (crumb.key)}
				<BreadcrumbItem isCurrentPage={i === crumbs.length - 1}>
					<button class="crumb" onclick={() => goToDir(crumb.key)}>{crumb.name}</button>
				</BreadcrumbItem>
			{/each}
		</Breadcrumb>
		<Toggle labelText="Include subfolders" size="sm" bind:toggled={includeSub} />
	</div>

	{#if !dataLoaded}
		<div class="card-flexbox">
			{#each Array(8) as _}
				<SkeletonPlaceholder style="width: var(--card-width); height: 12rem" />
			{/each}
		</div>
	{:else}
		{#if subfolders.length > 0}
			<div class="folder-grid">
				{#each subfolders as folder (folder.name)}
					<Tile class="folder-tile" on:click={() => goToDir(nodeKey(folder))}>
						<button class="folder-btn" onclick={() => goToDir(nodeKey(folder))}>
							<Folder size={20} />
							<span class="folder-name">{folder.name}</span>
							<span class="folder-count">
								{folder.totalCount}
								{#if folder.unreadCount > 0}<span class="unread">· {folder.unreadCount} unread</span
									>{/if}
							</span>
						</button>
					</Tile>
				{/each}
			</div>
		{/if}

		<PaginationContainer
			totalItems={displayFiles.length}
			page={filesInPage.length > 0 ? curPage : undefined}
			{pageSize}
			{onPaginationChange}
		>
			<div class="card-flexbox">
				{#if displayFiles.length === 0 && subfolders.length === 0}
					<div class="empty-state">
						<p>This folder is empty.</p>
					</div>
				{:else}
					{#each filesInPage as file, idx (file.id)}
						<div class="card-anim">
							<FileCard {file} light={idx % 2 === 0} onClickFile={() => onClickFile(file)} />
						</div>
					{/each}
				{/if}
			</div>
		</PaginationContainer>
	{/if}

	{#if page.state.showFileDetailModal && selectedFile}
		<FileDetailModal
			open
			onCloseModal={() => history.back()}
			bind:file={selectedFile}
			onClickTag={(tag) => goto(`/${mediaType}?q=${tag}`)}
			onClickPrimaryButton={() => {
				pushState('', { showFileDetailModal: false, showFileContent: true });
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
		padding: 0.5rem;
	}
	#hidelist {
		display: none;
	}
	.header-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		color: inherit;
		font: inherit;
	}
	.crumb:hover {
		text-decoration: underline;
	}
	.folder-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	:global(.folder-tile) {
		padding: 0 !important;
		min-width: 200px;
		flex: 1 1 200px;
		max-width: 280px;
	}
	.folder-btn {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.75rem;
		background: none;
		border: none;
		cursor: pointer;
		color: inherit;
		font: inherit;
		text-align: left;
	}
	.folder-name {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.875rem;
	}
	.folder-count {
		flex-shrink: 0;
		font-size: 0.75rem;
		color: var(--cds-text-02, #c6c6c6);
	}
	.unread {
		color: var(--cds-support-04, #4589ff);
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
</style>
