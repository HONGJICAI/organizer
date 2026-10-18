<script lang="ts">
	import {
		Breadcrumb,
		BreadcrumbItem,
		Select,
		SelectItem,
		SkeletonPlaceholder,
		Toggle
	} from 'carbon-components-svelte';
	import { Folder, Home } from 'carbon-icons-svelte';
	import { goto, pushState } from '$app/navigation';
	import { page } from '$app/state';
	import { MediaFile, MediaFileComparison, type MediaFileComparisonType } from '$lib/model.svelte';
	import { buildFolderTree, findNode, collectFiles, nodeKey } from '$lib/folderTree';
	import { getOrderByOptions } from '../orderByOptions.js';
	import FileCard from '$lib/components/FileCard.svelte';
	import FileDetailModal from '$lib/components/FileDetailModal.svelte';
	import FileContent from '$lib/components/FileContent.svelte';
	import PaginationContainer from '$lib/components/PaginationContainer.svelte';

	let { data } = $props();
	let dataLoaded = $state(false);
	let files = $state([] as MediaFile[]);
	$effect(() => {
		const pending = data.files;
		// reset immediately so a slow/failed load never shows the previous
		// media type's content (e.g. switching image -> empty/erroring video)
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

	let mediaType = $derived(page.params.mediaType);
	let includeSub = $state(false);
	let pageSize = $state(20);
	let selectedFile: MediaFile | undefined = $state();
	let orderBy = $state<MediaFileComparisonType>(MediaFileComparison.Name);
	let reverse = $state(false);
	let orderByOptions = $derived(files[0] ? getOrderByOptions(files[0].type) : []);

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
	// Sub-folders sort with the same control. Only Name and Size map to a
	// folder-level metric; for other criteria folders keep a stable name order.
	let subfolders = $derived.by(() => {
		if (includeSub) {
			return [];
		}
		const list = currentNode.children.slice();
		list.sort((a, b) => {
			const cmp =
				orderBy === MediaFileComparison.Size
					? a.totalSize - b.totalSize
					: a.name.localeCompare(b.name);
			return reverse ? -cmp : cmp;
		});
		return list;
	});
	let displayFiles = $derived(
		(includeSub ? collectFiles(currentNode) : currentNode.files)
			.slice()
			.sort((a, b) => (reverse ? -a.compareTo(b, orderBy) : a.compareTo(b, orderBy)))
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
	const formatSize = (mb: number) =>
		mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
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
					<button class="crumb" title={crumb.name} onclick={() => goToDir(crumb.key)}>
						<span class="crumb-name">{crumb.name}</span>
					</button>
				</BreadcrumbItem>
			{/each}
		</Breadcrumb>
		<div class="controls">
			{#if orderByOptions.length > 0}
				<Select size="sm" hideLabel bind:selected={orderBy}>
					{#each orderByOptions as { value, text } (value)}
						<SelectItem {value} {text} />
					{/each}
				</Select>
			{/if}
			<!-- No Off/On text: it overflows the label's width into the next toggle. -->
			<Toggle labelText="Reverse" labelA="" labelB="" size="sm" bind:toggled={reverse} />
			<Toggle
				labelText="Include subfolders"
				labelA=""
				labelB=""
				size="sm"
				bind:toggled={includeSub}
			/>
		</div>
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
					<button class="folder-tile" title={folder.name} onclick={() => goToDir(nodeKey(folder))}>
						<Folder size={20} />
						<span class="folder-name">{folder.name}</span>
						<span class="folder-meta">
							{folder.totalCount}
							{folder.totalCount === 1 ? 'item' : 'items'} · {formatSize(folder.totalSize)}
							{#if folder.unreadCount > 0}<span class="unread">· {folder.unreadCount} unread</span
								>{/if}
						</span>
					</button>
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
						<p>Nothing found in current folder</p>
						<p class="empty-hint">This folder has no items to show.</p>
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
	/* Long folder names (circle + author + notes) shouldn't push the
	   breadcrumb across several lines; the full name is in the tooltip. */
	.crumb-name {
		display: inline-block;
		max-width: 20rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		vertical-align: bottom;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
	}
	/* Equal-width columns that fill the row, one column on a phone. */
	.folder-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr));
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	/* Icon beside a name of up to two lines, with the counts underneath, so
	   the counts never eat into the name. */
	.folder-tile {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		column-gap: 0.625rem;
		row-gap: 0.25rem;
		align-items: start;
		padding: 0.75rem;
		background: var(--cds-ui-01, #262626);
		border: none;
		border-radius: 0.25rem;
		cursor: pointer;
		color: var(--cds-text-01, #f4f4f4);
		font: inherit;
		text-align: left;
	}
	.folder-tile:hover {
		background: var(--cds-hover-ui, #353535);
	}
	.folder-tile:focus-visible {
		outline: 2px solid var(--cds-focus, #ffffff);
		outline-offset: -2px;
	}
	.folder-name {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		overflow-wrap: anywhere;
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.folder-meta {
		grid-column: 2;
		font-size: 0.75rem;
		color: var(--cds-text-02, #c6c6c6);
	}
	.unread {
		color: var(--cds-support-04, #4589ff);
	}
	@media (max-width: 672px) {
		.crumb-name {
			max-width: 12rem;
		}
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
