<script lang="ts">
	import {
		Button,
		DataTable,
		Modal,
		Pagination,
		RadioButton,
		RadioButtonGroup,
		Select,
		SelectItem,
		Tag,
		Toolbar,
		ToolbarBatchActions,
		ToolbarContent,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { untrack } from 'svelte';
	import { adapters } from '$lib/mediaAdapters';
	import { ErrorNotification, SuccessNotification, type MediaFile } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { separateFilename } from '$lib/utility';
	import {
		classifierRows,
		kindColor,
		kindLabel,
		tagKinds,
		type ClassifierRow,
		type TagKind
	} from '$lib/tagIndex';
	import { loadTags, mergeTags, setTagKind, tagState } from '$lib/tags.svelte';

	// Manual tag classification: every tag of the list with its count, marked
	// as author / language / ignored, or merged as aliases. Aliases fold into
	// their primary's row (merges are one level deep), expanded to manage them.

	interface Props {
		files: MediaFile[];
		onClickTag?: (tag: string) => void;
	}
	let { files, onClickTag }: Props = $props();

	loadTags();

	type Filter = 'all' | 'none' | 'merged' | TagKind;
	let filter = $state<Filter>('none');
	let search = $state('');
	let page = $state(1);
	let pageSize = $state(50);
	let selectedRowIds = $state<string[]>([]);
	let expandedRowIds = $state<string[]>([]);
	let saving = $state(false);
	let mergeOpen = $state(false);
	let mergePrimary = $state('');

	const live = $derived(files.filter((f) => !f.archived));
	const sources = $derived(live.map((f) => adapters[f.type].tagSource(f)));
	const rows = $derived(classifierRows(sources, tagState.index).map((r) => ({ id: r.name, ...r })));
	const inFilter = (r: ClassifierRow, f: Filter) =>
		f === 'all' || (f === 'merged' ? r.aliases.length > 0 : f === 'none' ? !r.kind : r.kind === f);
	// A search matches a row by its name or any alias.
	const aliasHit = (r: ClassifierRow, q: string) =>
		r.aliases.some((a) => a.name.toLowerCase().includes(q));
	const filtered = $derived.by(() => {
		const q = search.toLowerCase();
		return rows.filter(
			(r) => inFilter(r, filter) && (!q || r.name.toLowerCase().includes(q) || aliasHit(r, q))
		);
	});
	const pageRows = $derived(filtered.slice((page - 1) * pageSize, page * pageSize));
	// Files with at least one author tag (through aliases too).
	const withAuthor = $derived(
		sources.filter((s) => separateFilename(s).some((t) => tagState.index.kind(t) === 'author'))
			.length
	);
	const filterCount = (f: Filter) => rows.filter((r) => inFilter(r, f)).length;
	const filters: { value: Filter; label: string }[] = [
		{ value: 'none', label: 'Unclassified' },
		...tagKinds.map((k) => ({ value: k, label: kindLabel[k] })),
		{ value: 'merged', label: 'Merged' },
		{ value: 'all', label: 'All' }
	];

	// Back to the first page when the list changes under the pager.
	$effect(() => {
		void filter;
		void search;
		page = 1;
	});

	// Open the rows a search found only through an alias, so the hit shows.
	// Only on a new search: edits inside an open row must not close it.
	$effect(() => {
		const q = search.toLowerCase();
		untrack(() => {
			expandedRowIds = q
				? filtered
						.filter((r) => !r.name.toLowerCase().includes(q) && aliasHit(r, q))
						.map((r) => r.id)
				: [];
		});
	});

	async function run(change: Promise<string | undefined>, done: string): Promise<boolean> {
		saving = true;
		const error = await change;
		saving = false;
		addNotification(
			error
				? new ErrorNotification({ subtitle: error })
				: new SuccessNotification({ subtitle: done })
		);
		return !error;
	}

	// An alias leaves the group unclassified (the primary and the rest stay).
	const splitOut = (alias: string) => run(setTagKind([alias], null), `${alias} split out`);
	// The old primary and its other aliases become aliases of the new one,
	// whose row stays open in place of the old one.
	async function makePrimary(alias: string, primary: string) {
		if (await run(mergeTags(alias, [primary]), `${alias} is now the primary tag`))
			expandedRowIds = [...expandedRowIds.filter((id) => id !== primary), alias];
	}

	async function apply(kind: TagKind | null) {
		saving = true;
		const names = [...selectedRowIds];
		const error = await setTagKind(names, kind);
		saving = false;
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error }));
			return;
		}
		addNotification(
			new SuccessNotification({
				subtitle: `${names.length} tag(s) ${kind ? `marked ${kindLabel[kind].toLowerCase()}` : 'unclassified'}`
			})
		);
		selectedRowIds = [];
	}

	// Unclassifying a primary forgets its aliases too (api/tags.py set_kind),
	// which the folded rows hide: confirm when that would happen.
	let unclassifyOpen = $state(false);
	const unclassifyAliases = $derived(
		rows.filter((r) => selectedRowIds.includes(r.id)).flatMap((r) => r.aliases.map((a) => a.name))
	);
	function unclassify() {
		if (unclassifyAliases.length) unclassifyOpen = true;
		else apply(null);
	}

	function openMerge() {
		// Default primary: an already classified tag, else the most used one.
		const selected = rows.filter((r) => selectedRowIds.includes(r.id));
		mergePrimary = (selected.find((r) => r.kind) ?? selected[0])?.name ?? '';
		mergeOpen = true;
	}

	async function merge() {
		mergeOpen = false;
		saving = true;
		const aliases = selectedRowIds.filter((n) => n !== mergePrimary);
		const error = await mergeTags(mergePrimary, aliases);
		saving = false;
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error }));
			return;
		}
		addNotification(
			new SuccessNotification({ subtitle: `${aliases.length} tag(s) merged into ${mergePrimary}` })
		);
		selectedRowIds = [];
	}
</script>

<p class="hint">
	Mark tags as authors or languages, or ignore noise such as release notes: the comic list's tag
	sidebar groups them, and Move to folder can gather every author. Merge tags that name the same
	thing (e.g. an author's romanized name) to make them aliases of one primary tag; aliases fold into
	the primary's row, and expanding it splits one out or makes it the primary.
	{#if live.length}
		<strong>{Math.round((withAuthor / live.length) * 100)}%</strong> of the {live.length} items have
		an author tag.
	{/if}
</p>

<DataTable
	expandable
	selectable
	batchSelection
	size="short"
	nonExpandableRowIds={pageRows.filter((r) => !r.aliases.length).map((r) => r.id)}
	headers={[
		{ key: 'name', value: 'Tag' },
		{ key: 'count', value: 'Items' },
		{ key: 'kind', value: 'Kind' }
	]}
	rows={pageRows}
	bind:selectedRowIds
	bind:expandedRowIds
>
	<svelte:fragment slot="cell" let:row let:cell>
		{#if cell.key === 'name'}
			<button class="tag-name" title="Show these items" onclick={() => onClickTag?.(row.name)}
				>{cell.value}</button
			>
			{#if row.aliases.length}
				<span class="muted" title={row.aliases.map((a: { name: string }) => a.name).join(', ')}>
					+{row.aliases.length} alias{row.aliases.length > 1 ? 'es' : ''}</span
				>
			{/if}
		{:else if cell.key === 'kind'}
			{#if row.kind}
				<Tag size="sm" type={kindColor[row.kind as TagKind]}>{kindLabel[row.kind as TagKind]}</Tag>
			{:else}
				<span class="muted">—</span>
			{/if}
		{:else}
			{cell.value}
		{/if}
	</svelte:fragment>
	<svelte:fragment slot="expanded-row" let:row>
		{#snippet itemCount(n: number)}
			<span class="muted">{n} item{n === 1 ? '' : 's'}</span>
		{/snippet}
		<!-- Every name of the group with the files that name it; the Items
		     column above counts each file once for the whole group. -->
		<ul class="aliases">
			<li>
				<button class="tag-name" title="Show these items" onclick={() => onClickTag?.(row.name)}
					>{row.name}</button
				>
				{@render itemCount(row.own)}
				<span><Tag size="sm" type="outline">Primary</Tag></span>
			</li>
			{#each row.aliases as alias (alias.name)}
				<li>
					<button class="tag-name" title="Show these items" onclick={() => onClickTag?.(alias.name)}
						>{alias.name}</button
					>
					{@render itemCount(alias.count)}
					<span>
						<Button
							size="small"
							kind="ghost"
							disabled={saving}
							on:click={() => makePrimary(alias.name, row.name)}>Make primary</Button
						>
						<Button
							size="small"
							kind="ghost"
							disabled={saving}
							on:click={() => splitOut(alias.name)}>Split out</Button
						>
					</span>
				</li>
			{/each}
		</ul>
	</svelte:fragment>
	<Toolbar>
		<ToolbarBatchActions>
			{#each tagKinds as kind (kind)}
				<Button disabled={saving} on:click={() => apply(kind)}>{kindLabel[kind]}</Button>
			{/each}
			<Button disabled={saving || selectedRowIds.length < 2} on:click={openMerge}>Merge…</Button>
			<Button disabled={saving} on:click={unclassify}>Unclassify</Button>
		</ToolbarBatchActions>
		<ToolbarContent>
			<ToolbarSearch bind:value={search} persistent placeholder="Search tags" />
			<Select size="sm" inline hideLabel labelText="Show" bind:selected={filter}>
				{#each filters as f (f.value)}
					<SelectItem value={f.value} text="{f.label} ({filterCount(f.value)})" />
				{/each}
			</Select>
		</ToolbarContent>
	</Toolbar>
</DataTable>
{#if filtered.length > pageSize}
	<Pagination bind:page bind:pageSize totalItems={filtered.length} pageSizes={[50, 100, 200]} />
{/if}
{#if filtered.length === 0}
	<p class="muted empty">No tags here.</p>
{/if}

<Modal
	bind:open={mergeOpen}
	modalHeading="Merge {selectedRowIds.length} tags"
	primaryButtonText="Merge"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (mergeOpen = false)}
	on:submit={merge}
>
	<p class="modal-text">
		The others become aliases of the primary tag: they count, search and move as one, under the
		primary's name and kind.
	</p>
	<RadioButtonGroup legendText="Primary tag" orientation="vertical" bind:selected={mergePrimary}>
		{#each selectedRowIds as name (name)}
			<RadioButton labelText={name} value={name} />
		{/each}
	</RadioButtonGroup>
</Modal>

<Modal
	danger
	bind:open={unclassifyOpen}
	modalHeading="Unclassify {selectedRowIds.length} tag(s)?"
	primaryButtonText="Unclassify"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (unclassifyOpen = false)}
	on:submit={() => {
		unclassifyOpen = false;
		apply(null);
	}}
>
	<p class="modal-text">
		Their {unclassifyAliases.length} alias(es) are unmerged and unclassified too:
	</p>
	<p class="muted">{unclassifyAliases.join(', ')}</p>
</Modal>

<style>
	.hint {
		max-width: 60rem;
		margin: 0 0 1rem;
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}
	.tag-name {
		background: none;
		border: none;
		padding: 0;
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
		overflow-wrap: anywhere;
	}
	.tag-name:hover {
		text-decoration: underline;
	}
	.muted {
		color: var(--cds-text-03, #8d8d8d);
	}
	.empty {
		margin: 1rem 0;
	}
	.modal-text {
		margin-bottom: 1rem;
	}
	/* Name, count and actions line up in columns across the group. */
	.aliases {
		display: grid;
		grid-template-columns: minmax(0, max-content) max-content 1fr;
		align-items: center;
		gap: 0.25rem 1.5rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.aliases li {
		display: contents;
	}
</style>
