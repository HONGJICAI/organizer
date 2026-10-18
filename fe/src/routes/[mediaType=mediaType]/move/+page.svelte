<script lang="ts">
	import { ComicsService, SystemService } from '$lib/client';
	import type { ComicMovePlanItem } from '$lib/client';
	import { errorMessage } from '$lib/mediaAdapters';
	import { ErrorNotification, SuccessNotification, type MediaFile } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { hasTag } from '$lib/moveTarget';
	import { folderKey } from '$lib/folderTree';
	import { loadTags, tagState } from '$lib/tags.svelte';
	import AuthorsOverview from '$lib/components/AuthorsOverview.svelte';
	import { goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		Checkbox,
		InlineLoading,
		InlineNotification,
		Link,
		Modal,
		Search,
		SkeletonPlaceholder,
		Tag,
		TextInput
	} from 'carbon-components-svelte';
	import { FolderMoveTo, Home, View } from 'carbon-icons-svelte';
	import { onDestroy } from 'svelte';

	let { data } = $props();
	let mediaType = $derived(page.params.mediaType);

	let files = $state([] as MediaFile[]);
	let dataLoaded = $state(false);
	$effect(() => {
		const pending = data.files;
		dataLoaded = false;
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

	let tagInput = $state(page.url.searchParams.get('tag') ?? '');
	let tag = $derived(page.url.searchParams.get('tag') ?? '');
	// A classified tag gathers its aliases too, under the primary name.
	loadTags();
	let tagNames = $derived(tag ? tagState.index.names(tag) : []);
	let folderTag = $derived(tag ? tagState.index.canonical(tag) : '');
	// Archived comics are records of deleted files: nothing to move.
	let matches = $derived(files.filter((f) => !f.archived && hasTag(f.name, tagNames)));
	let excluded = $state(new Set<number>());
	let selected = $derived(matches.filter((f) => !excluded.has(f.id)));
	let target = $state('');
	let preview = $state<ComicMovePlanItem[] | null>(null);
	let previewTarget = $state('');
	let previewing = $state(false);
	let previewError = $state('');
	let confirmOpen = $state(false);
	let runningJob = $state<number | null>(null);
	// Outcome of the last move, kept on the page until the next preview or tag.
	let result = $state<{
		ok: boolean;
		count: number;
		target: string;
		error: string | null;
	} | null>(null);
	// The target in the folder view, once the reloaded list knows it.
	let resultFolderKey = $derived(
		result
			? folderKey(
					files.filter((f) => !f.archived),
					result.target
				)
			: undefined
	);

	// A new tag starts over: everything selected, the suggested target, no preview.
	$effect(() => {
		tagInput = tag;
		excluded = new Set();
		preview = null;
		previewError = '';
		result = null;
	});
	// Suggested target from the backend: a folder named after the tag that
	// already holds some of these comics, else <artist folder>/<tag>.
	$effect(() => {
		const ids = matches.map((f) => f.id);
		const name = folderTag;
		if (!dataLoaded || !ids.length) return;
		let stale = false;
		ComicsService.comicMoveSuggest({ body: { ids, name } }).then(({ data }) => {
			if (!stale && data) target = data.target;
		});
		return () => {
			stale = true;
		};
	});

	const toMove = $derived(preview?.filter((i) => i.status === 'move') ?? []);
	const crossCount = $derived(toMove.filter((i) => i.crossDevice).length);
	const count = (status: ComicMovePlanItem['status']) =>
		preview?.filter((i) => i.status === status).length ?? 0;
	const statusTag: Record<
		ComicMovePlanItem['status'],
		{ type: 'green' | 'gray' | 'red' | 'magenta'; label: string }
	> = {
		move: { type: 'green', label: 'Move' },
		same: { type: 'gray', label: 'Already there' },
		conflict: { type: 'red', label: 'Conflict' },
		missing: { type: 'magenta', label: 'File missing' },
		notfound: { type: 'magenta', label: 'Not found' }
	};

	function applyTag() {
		const t = tagInput.trim();
		goto(t ? `?tag=${encodeURIComponent(t)}` : '?', { keepFocus: true });
	}

	function toggle(id: number, checked: boolean) {
		const next = new Set(excluded);
		if (checked) next.delete(id);
		else next.add(id);
		excluded = next;
		preview = null;
	}

	async function runPreview() {
		previewing = true;
		previewError = '';
		result = null;
		const { data, error } = await ComicsService.comicMovePreview({
			body: { ids: selected.map((f) => f.id), target }
		});
		previewing = false;
		if (error || !data) {
			preview = null;
			previewError = errorMessage(error);
			return;
		}
		preview = data.items;
		previewTarget = data.target;
	}

	async function move() {
		confirmOpen = false;
		const { data, error } = await ComicsService.comicMove({
			body: { ids: toMove.map((i) => i.id), target: previewTarget }
		});
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: errorMessage(error) }));
			return;
		}
		addNotification(new SuccessNotification({ subtitle: data.message }));
		runningJob = data.jobId;
		movingCount = toMove.length;
		poll();
	}

	// Follow the job until it lands in the history, then reload the list so
	// the comics show their new paths.
	let timer: ReturnType<typeof setTimeout> | undefined;
	let movingCount = 0;
	async function poll() {
		const { data } = await SystemService.listJobs();
		const done = data?.history.find((j) => j.id === runningJob);
		if (!done) {
			timer = setTimeout(poll, 1000);
			return;
		}
		runningJob = null;
		result = {
			ok: done.state === 'succeeded',
			count: movingCount,
			target: done.params.target ?? previewTarget,
			error: done.error ?? null
		};
		preview = null;
		refreshMediaFiles(mediaType);
		invalidate(`app:media:${mediaType}`);
	}
	onDestroy(() => clearTimeout(timer));
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/{mediaType}">
		<span class="crumb"><Home size={16} /><span>{mediaType}</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Move to folder</BreadcrumbItem>
</Breadcrumb>
<h1>Move to folder</h1>

{#if mediaType !== 'comic'}
	<p class="hint">Only comics can be moved for now.</p>
{:else}
	<p class="hint">
		Gather every comic with a tag (e.g. an author's <code>[name]</code>) into one folder. Comics
		keep their favorite, reading progress and cover: the record follows the file. The folder must be
		inside a comic scan folder and is created if needed. The suggestion is a folder named after the
		tag that already holds some of the comics, else one in the artist folder (<code
			>COMIC_ARTIST_PATH</code
		>, by default <code>artist/</code> in the comic folder). Moving within one drive is a quick rename;
		between drives or network shares the files are copied, then the originals deleted.
	</p>

	<div class="controls">
		<div class="tag-search">
			<Search
				placeholder="Tag, e.g. an author name"
				bind:value={tagInput}
				on:change={applyTag}
				on:clear={() => goto('?')}
			/>
		</div>
	</div>

	<!-- Only the first load shows a skeleton: a reload after a move keeps the
	     page (and its result banners) in place. -->
	{#if !dataLoaded && !files.length}
		<SkeletonPlaceholder style="width: 100%; height: 12rem" />
	{:else if !tag}
		<AuthorsOverview
			{files}
			{mediaType}
			onDone={() => {
				refreshMediaFiles(mediaType);
				invalidate(`app:media:${mediaType}`);
			}}
		/>
	{:else if matches.length === 0}
		<p class="muted">No comic has the tag “{tag}”.</p>
	{:else}
		<h4>{selected.length} of {matches.length} comics with “{folderTag}” selected</h4>
		{#if tagNames.length > 1}
			<p class="muted">Including its aliases: {tagNames.slice(1).join(', ')}.</p>
		{/if}
		<ul class="comics">
			{#each matches as f (f.id)}
				<li>
					<Checkbox
						checked={!excluded.has(f.id)}
						on:check={(e) => toggle(f.id, e.detail)}
						labelText={f.name}
					/>
					<span class="path" title={f.path}>{f.path}</span>
				</li>
			{/each}
		</ul>

		<div class="controls">
			<div class="target">
				<TextInput
					labelText="Target folder"
					bind:value={target}
					on:input={() => (preview = null)}
					placeholder="/data/comics/…"
				/>
			</div>
			<Button
				kind="tertiary"
				icon={View}
				disabled={!selected.length || !target.trim() || previewing || runningJob !== null}
				on:click={runPreview}>Preview</Button
			>
			{#if previewing}<InlineLoading description="Checking…" />{/if}
		</div>

		{#if result}
			<div class="result">
				<InlineNotification
					kind={result.ok ? 'success' : 'error'}
					title={result.ok ? 'Moved' : 'Move finished with problems'}
					subtitle={result.ok
						? `${result.count} comic(s) now in ${result.target}.`
						: (result.error ?? 'The move job failed.')}
					on:close={() => (result = null)}
				/>
				{#if resultFolderKey !== undefined}
					<Link href="/{mediaType}/folder?dir={encodeURIComponent(resultFolderKey)}"
						>Open the folder</Link
					>
				{/if}
			</div>
		{/if}

		{#if previewError}
			<InlineNotification
				kind="error"
				title="Can't move there"
				subtitle={previewError}
				hideCloseButton
			/>
		{/if}

		{#if preview}
			<p class="summary">
				Into <code>{previewTarget}</code>: {toMove.length} to move{#if count('same')}, {count(
						'same'
					)}
					already there{/if}{#if count('conflict')}, {count('conflict')} with conflicts (skipped){/if}{#if count('missing') + count('notfound')},
					{count('missing') + count('notfound')} unavailable{/if}.
			</p>
			{#if crossCount}
				<InlineNotification
					kind="warning"
					title="Different drive"
					subtitle="{crossCount} comic(s) are on another drive or share than the target: they'll be copied and then deleted, which can take a while over the network."
					hideCloseButton
				/>
			{/if}
			<ul class="plan">
				{#each preview as item (item.id)}
					<li>
						<Tag size="sm" type={statusTag[item.status].type}>{statusTag[item.status].label}</Tag>
						{#if item.crossDevice}<Tag size="sm" type="warm-gray">Copy</Tag>{/if}
						<span class="name">{item.name || `#${item.id}`}</span>
						{#if item.reason}<span class="muted">— {item.reason}</span>{/if}
					</li>
				{/each}
			</ul>
			<div class="controls">
				<Button
					icon={FolderMoveTo}
					disabled={!toMove.length || runningJob !== null}
					on:click={() => (confirmOpen = true)}>Move {toMove.length} comic(s)</Button
				>
				{#if runningJob !== null}<InlineLoading description="Moving… (see Admin → Jobs)" />{/if}
			</div>
		{/if}
	{/if}
{/if}

<Modal
	bind:open={confirmOpen}
	modalHeading="Move {toMove.length} comic(s)?"
	primaryButtonText="Move"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmOpen = false)}
	on:submit={move}
>
	<p>
		The files will be moved into <code>{previewTarget}</code>.{crossCount
			? ` ${crossCount} of them are copied across drives first.`
			: ''} The move runs as a background job, after any scan or cover run in progress.
	</p>
</Modal>

<style>
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}
	.hint {
		max-width: 60rem;
		margin: 0.5rem 0 1rem;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 1rem;
		margin: 1rem 0;
	}
	.tag-search {
		width: 24rem;
		max-width: 100%;
	}
	.target {
		flex: 1 1 24rem;
		min-width: 0;
	}
	.comics,
	.plan {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin: 0.5rem 0;
	}
	.comics li {
		min-width: 0;
	}
	.comics .path {
		display: block;
		/* Line up under the checkbox label. */
		padding-left: 1.625rem;
	}
	.path,
	.muted {
		font-size: 0.75rem;
		color: var(--cds-text-03, #8d8d8d);
		overflow-wrap: anywhere;
	}
	.plan li {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.result {
		margin: 1rem 0;
	}
	.result :global(.bx--inline-notification) {
		max-width: 48rem;
		margin-bottom: 0.25rem;
	}
	.summary {
		margin: 1rem 0 0.5rem;
		color: var(--cds-text-02, #c6c6c6);
	}
</style>
