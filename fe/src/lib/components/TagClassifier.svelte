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
	import { adapters } from '$lib/mediaAdapters';
	import { ErrorNotification, SuccessNotification, type MediaFile } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { genTagMap, separateFilename } from '$lib/utility';
	import { kindColor, kindLabel, tagKinds, type TagKind } from '$lib/tagIndex';
	import { loadTags, mergeTags, setTagKind, tagState } from '$lib/tags.svelte';

	// Manual tag classification: every tag of the list with its count, marked
	// as author / circle / language / ignored, or merged as aliases.

	interface Props {
		files: MediaFile[];
		onClickTag?: (tag: string) => void;
	}
	let { files, onClickTag }: Props = $props();

	loadTags();

	type Filter = 'all' | 'none' | 'alias' | TagKind;
	let filter = $state<Filter>('none');
	let search = $state('');
	let page = $state(1);
	let pageSize = $state(50);
	let selectedRowIds = $state<string[]>([]);
	let saving = $state(false);
	let mergeOpen = $state(false);
	let mergePrimary = $state('');

	const live = $derived(files.filter((f) => !f.archived));
	const sources = $derived(live.map((f) => adapters[f.type].tagSource(f)));
	const counts = $derived(genTagMap(sources));
	const rows = $derived(
		[...counts]
			.map(([name, count]) => {
				const row = tagState.index.row(name);
				return {
					id: name,
					name,
					count,
					kind: tagState.index.kind(name),
					alias: row?.canonical ?? null
				};
			})
			.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
	);
	const filtered = $derived(
		rows.filter((r) => {
			if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
			if (filter === 'all') return true;
			if (filter === 'alias') return r.alias !== null;
			if (filter === 'none') return !r.kind && r.alias === null;
			return r.kind === filter;
		})
	);
	const pageRows = $derived(filtered.slice((page - 1) * pageSize, page * pageSize));
	// Files with at least one author tag (through aliases too).
	const withAuthor = $derived(
		sources.filter((s) => separateFilename(s).some((t) => tagState.index.kind(t) === 'author'))
			.length
	);
	const filterCount = (f: Filter) =>
		f === 'all'
			? rows.length
			: rows.filter((r) =>
					f === 'alias'
						? r.alias !== null
						: f === 'none'
							? !r.kind && r.alias === null
							: r.kind === f
				).length;
	const filters: { value: Filter; label: string }[] = [
		{ value: 'none', label: 'Unclassified' },
		...tagKinds.map((k) => ({ value: k, label: kindLabel[k] })),
		{ value: 'alias', label: 'Aliases' },
		{ value: 'all', label: 'All' }
	];

	// Back to the first page when the list changes under the pager.
	$effect(() => {
		void filter;
		void search;
		page = 1;
	});

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

	function openMerge() {
		// Default primary: an already classified tag, else the most used one.
		const selected = rows.filter((r) => selectedRowIds.includes(r.id));
		mergePrimary = (selected.find((r) => r.kind && !r.alias) ?? selected[0])?.name ?? '';
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
	Mark tags as authors, circles or languages, or ignore noise such as release notes: the comic
	list's tag sidebar groups them, and Move to folder can gather every author. Merge tags that name
	the same thing (e.g. an author's romanized name) to make them aliases of one primary tag.
	{#if live.length}
		<strong>{Math.round((withAuthor / live.length) * 100)}%</strong> of the {live.length} items have
		an author tag.
	{/if}
</p>

<DataTable
	selectable
	batchSelection
	size="short"
	headers={[
		{ key: 'name', value: 'Tag' },
		{ key: 'count', value: 'Items' },
		{ key: 'kind', value: 'Kind' }
	]}
	rows={pageRows}
	bind:selectedRowIds
>
	<svelte:fragment slot="cell" let:row let:cell>
		{#if cell.key === 'name'}
			<button class="tag-name" title="Show these items" onclick={() => onClickTag?.(row.name)}
				>{cell.value}</button
			>
		{:else if cell.key === 'kind'}
			{#if row.alias}
				<Tag size="sm" type="outline">Alias of {row.alias}</Tag>
			{:else if row.kind}
				<Tag size="sm" type={kindColor[row.kind as TagKind]}>{kindLabel[row.kind as TagKind]}</Tag>
			{:else}
				<span class="muted">—</span>
			{/if}
		{:else}
			{cell.value}
		{/if}
	</svelte:fragment>
	<Toolbar>
		<ToolbarBatchActions>
			{#each tagKinds as kind (kind)}
				<Button disabled={saving} on:click={() => apply(kind)}>{kindLabel[kind]}</Button>
			{/each}
			<Button disabled={saving || selectedRowIds.length < 2} on:click={openMerge}>Merge…</Button>
			<Button disabled={saving} on:click={() => apply(null)}>Unclassify</Button>
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
</style>
