<script lang="ts">
	import { ComicsService, SystemService } from '$lib/client';
	import type { ComicMovePlanItem } from '$lib/client';
	import { errorMessage } from '$lib/mediaAdapters';
	import type { MediaFile } from '$lib/model.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { folderKey } from '$lib/folderTree';
	import {
		authorGroups,
		sortGroups,
		tagGroup,
		type GroupComic,
		type MoveGroup
	} from '$lib/moveGroups';
	import { loadTags, tagState } from '$lib/tags.svelte';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		Checkbox,
		DataTable,
		DataTableSkeleton,
		InlineLoading,
		InlineNotification,
		Link,
		Modal,
		Pagination,
		Tag,
		TextInput,
		Toggle,
		Toolbar,
		ToolbarBatchActions,
		ToolbarContent,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { FolderMoveTo, Home } from 'carbon-icons-svelte';
	import { onDestroy } from 'svelte';

	// One table: a row per author (or any tag searched for), expanded into its
	// comics with where each goes. Targets come from the backend's suggestion
	// and can be edited per row; an expanded row previews its move as it
	// changes. Moves are one queued job per row.

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
	loadTags();

	// ?tag= (e.g. from the comic list) searches for and opens that row.
	let urlTag = $derived(page.url.searchParams.get('tag')?.trim() ?? '');
	let search = $state('');
	let showDone = $state(false);
	let pageNo = $state(1);
	let pageSize = $state(50);
	let selectedRowIds = $state<string[]>([]);
	let expandedRowIds = $state<string[]>([]);

	const authors = $derived(authorGroups(files, tagState.index));
	// A searched tag that isn't an author gets a row of its own.
	const extra = $derived.by(() => {
		const t = search.trim();
		if (!t || authors.some((g) => g.names.includes(t))) return null;
		return tagGroup(files, tagState.index, t);
	});
	const groups = $derived(sortGroups(extra ? [extra, ...authors] : [...authors]));
	const byKey = $derived(new Map(groups.map((g) => [g.key, g])));

	// Per row, keyed by the row's primary tag.
	let suggested = $state<Record<string, string>>({});
	let edited = $state<Record<string, string>>({});
	let picked = $state<Record<string, number[]>>({});
	let previews = $state<
		Record<string, { items?: ComicMovePlanItem[]; target?: string; error?: string }>
	>({});
	let results = $state<
		Record<
			string,
			{ state: 'queued' | 'moving' | 'done' | 'failed'; jobId: number; error?: string }
		>
	>({});

	const target = (key: string) => edited[key] ?? suggested[key] ?? '';
	const chosen = (g: MoveGroup) => picked[g.key] ?? g.pending;
	const chosenOf = (key: string) => {
		const g = byKey.get(key);
		return g ? chosen(g) : [];
	};
	const crossCount = (key: string) =>
		previews[key]?.items?.filter((i) => i.status === 'move' && i.crossDevice).length ?? 0;
	const busy = (key: string) => ['queued', 'moving'].includes(results[key]?.state ?? '');

	const visible = $derived(
		groups.filter((g) => {
			const q = search.trim().toLowerCase();
			if (q && !g.names.some((n) => n.toLowerCase().includes(q))) return false;
			return showDone || chosen(g).length > 0 || g === extra || results[g.key] !== undefined;
		})
	);
	const doneCount = $derived(groups.filter((g) => !g.pending.length).length);
	const rows = $derived(
		visible.slice((pageNo - 1) * pageSize, pageNo * pageSize).map((g) => ({
			id: g.key,
			name: g.key,
			comics: g.comics.length,
			move: chosen(g).length,
			target: target(g.key),
			status: ''
		}))
	);
	const workKeys = $derived(
		visible.filter((g) => chosen(g).length && !busy(g.key)).map((g) => g.key)
	);
	const sumChosen = (keys: string[]) => keys.reduce((n, k) => n + chosenOf(k).length, 0);
	$effect(() => {
		void search;
		void showDone;
		pageNo = 1;
	});

	// Follow ?tag=: search for it, and open its row once that exists.
	let openedUrlTag: string | null = null;
	$effect(() => {
		search = urlTag;
	});
	$effect(() => {
		if (!urlTag || openedUrlTag === urlTag || !dataLoaded) return;
		const key = tagState.index.canonical(urlTag);
		if (byKey.has(key)) {
			openedUrlTag = urlTag;
			expandedRowIds = [key];
		}
	});

	// Suggested targets for every row, fetched in one request whenever rows
	// without one show up.
	$effect(() => {
		const missing = groups.filter((g) => !(g.key in suggested));
		if (!missing.length) return;
		for (const g of missing) suggested[g.key] = '';
		ComicsService.comicMoveSuggest({
			body: { groups: missing.map((g) => ({ ids: g.comics.map((c) => c.id), name: g.key })) }
		}).then(({ data }) => {
			data?.targets.forEach((t, i) => (suggested[missing[i].key] = t));
		});
	});

	// Expanded rows preview their move whenever the target or the comics'
	// paths change (debounced while typing a target).
	const previewed: Record<string, string> = {};
	const timers = new Map<string, ReturnType<typeof setTimeout>>();
	$effect(() => {
		for (const key of expandedRowIds) {
			const g = byKey.get(key);
			if (!g) continue;
			const ids = g.comics.map((c) => c.id);
			const to = target(key);
			const sig = `${to}\n${g.comics.map((c) => c.path).join('\n')}`;
			if (!to || previewed[key] === sig) continue;
			previewed[key] = sig;
			clearTimeout(timers.get(key));
			timers.set(
				key,
				setTimeout(async () => {
					const { data, error } = await ComicsService.comicMovePreview({
						body: { ids, target: to }
					});
					if (previewed[key] !== sig) return;
					previews[key] = data
						? { items: data.items, target: data.target }
						: { error: errorMessage(error) };
				}, 400)
			);
		}
	});

	// Carbon's Checkbox also fires `check` on mount, so this must be idempotent.
	function toggle(g: MoveGroup, id: number, on: boolean) {
		const now = chosen(g);
		if (on === now.includes(id)) return;
		picked[g.key] = on ? [...now, id] : now.filter((x) => x !== id);
	}

	// --- Moving ---------------------------------------------------------------
	let confirmKeys = $state<string[]>([]);
	let confirmOpen = $state(false);
	const confirmCross = $derived(confirmKeys.reduce((n, k) => n + crossCount(k), 0));
	let summary = $state<{ moved: number; failed: string[] } | null>(null);

	function ask(keys: string[]) {
		confirmKeys = keys.filter((k) => chosenOf(k).length && target(k));
		if (confirmKeys.length) confirmOpen = true;
	}

	async function move() {
		confirmOpen = false;
		summary = null;
		const keys = confirmKeys;
		selectedRowIds = [];
		for (const key of keys) {
			const { data, error } = await ComicsService.comicMove({
				body: { ids: chosenOf(key), target: target(key) }
			});
			results[key] = data
				? { state: 'queued', jobId: data.jobId }
				: { state: 'failed', jobId: 0, error: errorMessage(error) };
		}
		poll(keys);
	}

	let pollTimer: ReturnType<typeof setTimeout> | undefined;
	onDestroy(() => {
		clearTimeout(pollTimer);
		timers.forEach(clearTimeout);
	});

	// Follow the jobs until none is waiting or running. History keeps the last
	// 20 jobs, so one that dropped out of it counts as done.
	async function poll(keys: string[]) {
		const { data } = await SystemService.listJobs();
		if (data) {
			for (const key of keys) {
				const r = results[key];
				if (!r || r.state === 'failed' || r.state === 'done') continue;
				const finished = data.history.find((j) => j.id === r.jobId);
				if (data.running?.id === r.jobId) r.state = 'moving';
				else if (finished)
					results[key] =
						finished.state === 'succeeded'
							? { ...r, state: 'done' }
							: { ...r, state: 'failed', error: finished.error ?? finished.state };
				else if (!data.queued.some((j) => j.id === r.jobId)) r.state = 'done';
			}
		}
		if (keys.some((k) => busy(k))) {
			pollTimer = setTimeout(() => poll(keys), 1500);
			return;
		}
		const failed = keys
			.filter((k) => results[k]?.state === 'failed')
			.map((k) => `${k}: ${results[k].error}`);
		summary = { moved: keys.length - failed.length, failed };
		// Moved comics are pending no more; drop picks made before the move.
		for (const key of keys) delete picked[key];
		refreshMediaFiles(mediaType);
		invalidate(`app:media:${mediaType}`);
	}

	const planTag: Record<
		ComicMovePlanItem['status'],
		{ type: 'green' | 'gray' | 'red' | 'magenta'; label: string }
	> = {
		move: { type: 'green', label: 'Move' },
		same: { type: 'gray', label: 'Already there' },
		conflict: { type: 'red', label: 'Conflict' },
		missing: { type: 'magenta', label: 'File missing' },
		notfound: { type: 'magenta', label: 'Not found' }
	};
	const folderHref = (key: string) => {
		const k = folderKey(
			files.filter((f) => !f.archived),
			previews[key]?.target ?? target(key)
		);
		return k === undefined ? undefined : `/${mediaType}/folder?dir=${encodeURIComponent(k)}`;
	};
</script>

{#snippet comicState(c: GroupComic, item: ComicMovePlanItem | undefined, previewed: boolean)}
	{#if c.otherAuthors.length}
		<Tag size="sm" type="outline" title="Several authors: pick where it goes"
			>also {c.otherAuthors.join(', ')}</Tag
		>
	{/if}
	{#if item}
		<Tag size="sm" type={planTag[item.status].type} title={item.reason ?? ''}
			>{planTag[item.status].label}</Tag
		>
		{#if item.crossDevice}<Tag size="sm" type="warm-gray">Copy</Tag>{/if}
		{#if item.reason}<span class="muted">{item.reason}</span>{/if}
	{:else if c.inPlace}
		<Tag size="sm" type="gray">Already there</Tag>
	{:else if !previewed}
		<span class="muted">…</span>
	{/if}
{/snippet}

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/{mediaType}">
		<span class="crumb"><Home size={16} /><span>{mediaType}</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Move to folder</BreadcrumbItem>
</Breadcrumb>
<h1>Move to folder</h1>

{#if mediaType !== 'comic'}
	<p class="hint">Only comics can be moved for now.</p>
{:else if !dataLoaded && !files.length}
	<DataTableSkeleton rows={8} columns={5} />
{:else}
	<p class="hint">
		Gather each author's comics into one folder. Authors come from
		<Link href="/{mediaType}/tag?view=classify">Tags → Classify</Link>; search to gather any other
		tag.
	</p>
	<details class="how">
		<summary>How it works</summary>
		<p>
			Comics keep their favorite, progress and cover: the record follows the file. A row's folder is
			the one already named after it, else one in the artist folder (<code>COMIC_ARTIST_PATH</code
			>); expand a row to edit it and see where each comic goes. Within one drive a move is a
			rename; between drives or shares the files are copied, then deleted (marked <em>Copy</em>).
			Each row is its own background job (Admin → Jobs); comics that conflict are skipped.
		</p>
	</details>

	{#if summary}
		<InlineNotification
			kind={summary.failed.length ? 'warning' : 'success'}
			title={summary.failed.length ? 'Moved with problems' : 'Moved'}
			subtitle={`${summary.moved} row(s) done.${summary.failed.length ? ' ' + summary.failed.join('; ') : ''}`}
			on:close={() => (summary = null)}
		/>
	{/if}

	<div class="above">
		<Toggle
			size="sm"
			labelText="Show organized authors ({doneCount})"
			labelA=""
			labelB=""
			bind:toggled={showDone}
		/>
	</div>

	<DataTable
		expandable
		selectable
		batchSelection
		size="medium"
		class="move-table"
		nonSelectableRowIds={visible.filter((g) => !chosen(g).length || busy(g.key)).map((g) => g.key)}
		headers={[
			{ key: 'name', value: 'Author / tag' },
			{ key: 'comics', value: 'Comics' },
			{ key: 'move', value: 'To move' },
			{ key: 'target', value: 'Target folder' },
			{ key: 'status', value: 'Status' }
		]}
		{rows}
		bind:selectedRowIds
		bind:expandedRowIds
	>
		<svelte:fragment slot="cell" let:row let:cell>
			{@const g = byKey.get(row.id)}
			{#if cell.key === 'name'}
				<span class="name">{cell.value}</span>
				{#if g && !g.isAuthor}<Tag size="sm" type="outline">tag</Tag>{/if}
				{#if g && g.names.length > 1}
					<span class="muted" title={g.names.slice(1).join(', ')}>
						+{g.names.length - 1} alias{g.names.length > 2 ? 'es' : ''}</span
					>
				{/if}
			{:else if cell.key === 'target'}
				<span class="path" title={cell.value}>{cell.value || '…'}</span>
			{:else if cell.key === 'move'}
				{cell.value || '—'}
			{:else if cell.key === 'status'}
				{@const r = results[row.id]}
				{#if r?.state === 'queued'}
					<InlineLoading description="Queued" />
				{:else if r?.state === 'moving'}
					<InlineLoading description="Moving…" />
				{:else if r?.state === 'failed'}
					<Tag size="sm" type="red" title={r.error}>Failed</Tag>
				{:else if r?.state === 'done' && !row.move}
					<Tag size="sm" type="green">Moved</Tag>
				{:else if row.move}
					<span>{row.move} to move</span>
					{#if crossCount(row.id)}<Tag size="sm" type="warm-gray">{crossCount(row.id)} copy</Tag
						>{/if}
				{:else}
					<span class="muted">✓ Organized</span>
				{/if}
			{:else}
				{cell.value}
			{/if}
		</svelte:fragment>

		<svelte:fragment slot="expanded-row" let:row>
			{@const g = byKey.get(row.id)}
			{#if g}
				{@const p = previews[g.key]}
				{@const plan = new Map((p?.items ?? []).map((i) => [i.id, i]))}
				<div class="detail">
					<div class="target-row">
						<TextInput
							size="sm"
							labelText="Target folder"
							value={target(g.key)}
							on:input={(e) => (edited[g.key] = String(e.detail ?? ''))}
						/>
						{#if g.key in edited && edited[g.key] !== suggested[g.key]}
							<Button size="small" kind="ghost" on:click={() => delete edited[g.key]}
								>Use suggestion</Button
							>
						{/if}
					</div>
					{#if p?.error}
						<InlineNotification
							lowContrast
							kind="error"
							title="Can't move there"
							subtitle={p.error}
							hideCloseButton
						/>
					{/if}
					<table class="comics">
						<tbody>
							{#each g.comics as c (c.id)}
								{@const item = plan.get(c.id)}
								<tr>
									<td class="check">
										<Checkbox
											hideLabel
											labelText={`Move ${c.name}`}
											checked={chosen(g).includes(c.id)}
											disabled={busy(g.key)}
											on:check={(e) => toggle(g, c.id, e.detail)}
										/>
									</td>
									<td>
										<div class="comic-name">{c.name}</div>
										<div class="muted path" title={c.folder}>{c.folder}</div>
										<!-- On a phone the state column is hidden and shows here. -->
										<div class="state-inline">{@render comicState(c, item, !!p)}</div>
									</td>
									<td class="state">{@render comicState(c, item, !!p)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
					<div class="actions">
						<Button
							size="small"
							icon={FolderMoveTo}
							disabled={!chosen(g).length || !target(g.key) || busy(g.key)}
							on:click={() => ask([g.key])}
							>Move {chosen(g).length} comic{chosen(g).length === 1 ? '' : 's'}</Button
						>
						{#if results[g.key]?.state === 'done' && folderHref(g.key)}
							<Link href={folderHref(g.key)}>Open the folder</Link>
						{/if}
					</div>
				</div>
			{/if}
		</svelte:fragment>

		<Toolbar>
			<ToolbarBatchActions>
				<Button icon={FolderMoveTo} on:click={() => ask(selectedRowIds)}
					>Move selected ({sumChosen(selectedRowIds)} comics)</Button
				>
			</ToolbarBatchActions>
			<ToolbarContent>
				<ToolbarSearch persistent bind:value={search} placeholder="Search authors or any tag" />
				<Button icon={FolderMoveTo} disabled={!workKeys.length} on:click={() => ask(workKeys)}
					>Gather all ({sumChosen(workKeys)})</Button
				>
			</ToolbarContent>
		</Toolbar>
	</DataTable>
	{#if visible.length > pageSize}
		<Pagination
			bind:page={pageNo}
			bind:pageSize
			totalItems={visible.length}
			pageSizes={[50, 100, 200]}
		/>
	{/if}
	{#if !visible.length}
		<p class="hint empty">
			{#if search.trim()}
				No author or tag matches “{search.trim()}”.
			{:else if authors.length}
				Every author is organized. Turn on “Show organized” to see them.
			{:else}
				No authors yet: mark tags as authors under
				<Link href="/{mediaType}/tag?view=classify">Tags → Classify</Link>, or search for a tag.
			{/if}
		</p>
	{/if}
{/if}

<Modal
	bind:open={confirmOpen}
	modalHeading="Move {sumChosen(confirmKeys)} comic{sumChosen(confirmKeys) === 1 ? '' : 's'}?"
	primaryButtonText="Move"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmOpen = false)}
	on:submit={move}
>
	<p>
		{confirmKeys.length === 1
			? `Into ${target(confirmKeys[0])}.`
			: `${confirmKeys.length} rows, each into its own folder.`}
		{confirmCross ? `${confirmCross} are copied across drives first.` : ''}
		Each row is a background job, after any scan or cover run in progress; comics that conflict are skipped.
	</p>
</Modal>

<style>
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}
	.how {
		margin: -0.5rem 0 1rem;
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}
	.how summary {
		cursor: pointer;
		color: var(--cds-link-01, #78a9ff);
	}
	.how p {
		max-width: 60rem;
		margin-top: 0.5rem;
	}
	.hint {
		margin: 0.25rem 0 1rem;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
	}
	.empty {
		margin-top: 1rem;
	}
	.name {
		overflow-wrap: break-word;
		margin-right: 0.25rem;
	}
	.muted {
		color: var(--cds-text-03, #8d8d8d);
		font-size: 0.75rem;
	}
	.path {
		display: inline-block;
		max-width: 24rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		vertical-align: bottom;
	}
	.above {
		margin-bottom: 0.5rem;
	}
	/* On a phone, drop the Comics and Target columns (the target shows when a
	   row is expanded) so names don't break mid-word. Columns: expand,
	   checkbox, name, comics, to move, target, status. */
	@media (max-width: 672px) {
		:global(.move-table th:nth-child(4)),
		:global(.move-table td:nth-child(4)),
		:global(.move-table th:nth-child(6)),
		:global(.move-table td:nth-child(6)) {
			display: none;
		}
	}
	.detail {
		padding: 0.5rem 0 1rem;
	}
	.target-row {
		display: flex;
		align-items: flex-end;
		gap: 0.5rem;
		max-width: 48rem;
		margin-bottom: 0.75rem;
	}
	/* Fixed layout so long folder paths truncate instead of widening the page. */
	.comics {
		width: 100%;
		border-collapse: collapse;
		table-layout: fixed;
	}
	/* Inside the DataTable, Carbon's fixed row height would clip a comic
	   whose name or tags wrap. */
	.comics tr,
	.comics td {
		height: auto;
		background: transparent;
	}
	.comics td {
		padding: 0.375rem 0.5rem 0.375rem 0;
		vertical-align: top;
		border-top: 1px solid var(--cds-ui-03, #393939);
	}
	.comics .check {
		width: 2rem;
	}
	.comic-name {
		overflow-wrap: anywhere;
	}
	.comics .path {
		max-width: 100%;
	}
	.state {
		width: 40%;
	}
	.state-inline {
		display: none;
		margin-top: 0.25rem;
	}
	@media (max-width: 672px) {
		.comics td.state {
			display: none;
		}
		.state-inline {
			display: block;
		}
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-top: 0.75rem;
	}
</style>
