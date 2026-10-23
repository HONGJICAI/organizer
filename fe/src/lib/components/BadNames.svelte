<script lang="ts">
	import { adapterFor } from '$lib/mediaAdapters';
	import type { MediaFile } from '$lib/model.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import {
		checkName,
		problemLabels,
		splitExtension,
		type NameProblem,
		type NameProblemKind
	} from '$lib/nameCheck';
	import { separateFilename } from '$lib/utility';
	import {
		Button,
		DataTable,
		DataTableSkeleton,
		Dropdown,
		Modal,
		Pagination,
		Tag,
		TextInput,
		Toggle,
		Toolbar,
		ToolbarContent,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { Edit } from 'carbon-icons-svelte';

	// Comic names the tag splitter reads wrong (Cleanup → Bad names), with an
	// in-place rename that previews the tags the new name gives.

	let { mediaType, files }: { mediaType: string; files?: Promise<MediaFile[]> } = $props();

	let list = $state<MediaFile[]>([]);
	let loaded = $state(false);
	$effect(() => {
		let cancelled = false;
		loaded = false;
		files
			?.then((f) => {
				if (!cancelled) list = f;
			})
			.catch(() => {
				if (!cancelled) list = [];
			})
			.finally(() => {
				if (!cancelled) loaded = true;
			});
		return () => {
			cancelled = true;
		};
	});

	// Names changed here, until the list is fetched again.
	let renamed = $state<Record<number, string>>({});
	let showUntagged = $state(false);
	let kind = $state<NameProblemKind | 'all'>('all');
	let search = $state('');
	let pageNo = $state(1);
	let pageSize = $state(50);

	const nameOf = (f: MediaFile) => renamed[f.id] ?? f.name;
	const shown = (p: NameProblem) => showUntagged || p.kind !== 'untagged';
	const checked = $derived(
		list
			.filter((f) => !f.archived)
			.map((f) => ({ id: f.id, name: nameOf(f), problems: checkName(nameOf(f)).filter(shown) }))
			.filter((r) => r.problems.length)
	);
	const counts = $derived(
		checked.reduce(
			(m, r) => {
				for (const k of new Set(r.problems.map((p) => p.kind))) m[k] = (m[k] ?? 0) + 1;
				return m;
			},
			{} as Partial<Record<NameProblemKind, number>>
		)
	);
	const kinds = $derived([
		{ id: 'all', text: `All problems (${checked.length})` },
		...(Object.keys(problemLabels) as NameProblemKind[])
			.filter((k) => counts[k])
			.map((k) => ({ id: k, text: `${problemLabels[k]} (${counts[k]})` }))
	]);
	const rows = $derived(
		checked.filter(
			(r) =>
				(kind === 'all' || r.problems.some((p) => p.kind === kind)) &&
				r.name.toLowerCase().includes(search.trim().toLowerCase())
		)
	);
	const pageRows = $derived(
		rows
			.slice((pageNo - 1) * pageSize, pageNo * pageSize)
			.map((r) => ({ ...r, tags: separateFilename(r.name), edit: '' }))
	);
	$effect(() => {
		void kind;
		void search;
		void showUntagged;
		pageNo = 1;
	});
	// A kind filtered away by the untagged toggle shows everything instead.
	$effect(() => {
		if (kind !== 'all' && !counts[kind]) kind = 'all';
	});

	// The name with the first problem's character marked.
	function marked(name: string, problems: NameProblem[]) {
		const at = problems.find((p) => p.at >= 0)?.at ?? -1;
		return at < 0
			? { before: name, mark: '', after: '' }
			: { before: name.slice(0, at), mark: name[at], after: name.slice(at + 1) };
	}

	// --- Rename ---------------------------------------------------------------
	let editing = $state<{ id: number; name: string; ext: string; stem: string } | null>(null);
	let saving = $state(false);
	const newName = $derived(editing ? editing.stem.trim() + editing.ext : '');
	const preview = $derived(editing ? checkName(newName).filter(shown) : []);
	const renameProblem = $derived(
		!editing
			? ''
			: !editing.stem.trim()
				? 'Enter a name'
				: /[/\\]/.test(editing.stem)
					? 'A name can’t contain / or \\'
					: newName === editing.name
						? 'Unchanged'
						: ''
	);

	function edit(id: number, name: string) {
		const [stem, ext] = splitExtension(name);
		editing = { id, name, ext, stem };
	}

	async function save() {
		const adapter = adapterFor(mediaType);
		if (!editing || renameProblem || !adapter?.rename) return;
		saving = true;
		const { id, name } = editing;
		const { error } = await adapter.rename(id, newName);
		saving = false;
		if (error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: `Rename failed: ${error}` }));
			return;
		}
		renamed[id] = newName;
		editing = null;
		// Other views hold the old name; the next visit fetches the list again.
		refreshMediaFiles(mediaType);
		addNotification(new SuccessNotification({ subtitle: `Renamed ${name} → ${newName}` }));
	}
</script>

<p class="hint">
	Tags come from the brackets in a comic's name: <code>[Author] Title (Event).zip</code>. Names with
	unbalanced brackets are read wrong. An unclosed bracket drops every tag of the name, so the comic
	has no author and is missing from tag lists and Move to folder. Renaming changes the file on disk
	and keeps the comic's favorite and progress.
</p>

{#if !loaded}
	<DataTableSkeleton
		rows={10}
		headers={[
			{ key: 'name', value: 'Name' },
			{ key: 'problems', value: 'Problem' },
			{ key: 'tags', value: 'Tags as read now' },
			{ key: 'edit', empty: true }
		]}
	/>
{:else}
	<div class="table">
		<DataTable
			headers={[
				{ key: 'name', value: 'Name' },
				{ key: 'problems', value: 'Problem' },
				{ key: 'tags', value: 'Tags as read now' },
				{ key: 'edit', empty: true, width: '4rem' }
			]}
			rows={pageRows}
		>
			<svelte:fragment slot="cell" let:row let:cell>
				{#if cell.key === 'name'}
					{@const m = marked(row.name, row.problems)}
					<span class="name" title={row.name}
						>{m.before}{#if m.mark}<mark>{m.mark}</mark>{/if}{m.after}</span
					>
				{:else if cell.key === 'problems'}
					<span class="problems">
						{#each row.problems as p, i (i)}
							<Tag size="sm" type={p.kind === 'untagged' ? 'gray' : 'red'} title={p.message}
								>{problemLabels[p.kind]}</Tag
							>
						{/each}
					</span>
				{:else if cell.key === 'tags'}
					{#if row.tags.length}
						<span class="tags">{row.tags.join(' · ')}</span>
					{:else}
						<span class="muted">none</span>
					{/if}
				{:else if cell.key === 'edit'}
					<Button
						kind="ghost"
						size="small"
						icon={Edit}
						iconDescription="Rename"
						on:click={() => edit(row.id, row.name)}
					/>
				{/if}
			</svelte:fragment>
			<Toolbar>
				<ToolbarContent>
					<ToolbarSearch bind:value={search} placeholder="Search names" />
					<Dropdown
						size="sm"
						type="inline"
						items={kinds}
						selectedId={kind}
						on:select={(e) => (kind = e.detail.selectedId as typeof kind)}
					/>
					<Toggle size="sm" labelA="" labelB="" bind:toggled={showUntagged}>
						<span slot="labelText" class="toggle-label">Include names without tags</span>
					</Toggle>
				</ToolbarContent>
			</Toolbar>
		</DataTable>
	</div>
	{#if rows.length > pageSize}
		<Pagination
			bind:page={pageNo}
			bind:pageSize
			totalItems={rows.length}
			pageSizes={[25, 50, 100]}
		/>
	{/if}
	{#if !rows.length}
		<p class="empty">
			{checked.length ? 'Nothing matches the search.' : 'Every comic name reads cleanly. 🎉'}
		</p>
	{/if}
{/if}

<Modal
	open={editing !== null}
	modalHeading="Rename comic"
	primaryButtonText={saving ? 'Renaming…' : 'Rename'}
	primaryButtonDisabled={!!renameProblem || saving}
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (editing = null)}
	on:close={() => (editing = null)}
	on:submit={save}
>
	{#if editing}
		<p class="muted old" title={editing.name}>{editing.name}</p>
		<TextInput
			labelText="New name{editing.ext ? ` (${editing.ext} is kept)` : ''}"
			bind:value={editing.stem}
			invalid={!!renameProblem && renameProblem !== 'Unchanged'}
			invalidText={renameProblem}
		/>
		<h5>Tags it gives</h5>
		<p class="tags">
			{#each separateFilename(newName) as tag (tag)}
				<Tag size="sm">{tag}</Tag>
			{:else}
				<span class="muted">none</span>
			{/each}
		</p>
		{#if preview.length}
			<ul class="preview">
				{#each preview as p, i (i)}
					<li><Tag size="sm" type="red">{problemLabels[p.kind]}</Tag> {p.message}</li>
				{/each}
			</ul>
		{:else}
			<p class="ok">The name reads cleanly.</p>
		{/if}
	{/if}
</Modal>

<style>
	.hint {
		max-width: 60rem;
		margin: 0.5rem 0 1rem;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
	}

	.name {
		overflow-wrap: anywhere;
	}

	.problems :global(.bx--tag) {
		white-space: nowrap;
	}

	/* No room for the parsed tags on a phone; the problem column says enough. */
	@media (max-width: 671px) {
		.table :global(th:nth-child(3)),
		.table :global(td:nth-child(3)) {
			display: none;
		}
	}

	mark {
		background: var(--cds-support-01, #fa4d56);
		color: var(--cds-text-on-color, #fff);
		padding: 0 0.15em;
		border-radius: 2px;
	}

	.problems {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.tags {
		overflow-wrap: anywhere;
	}

	.muted {
		color: var(--cds-text-02, #c6c6c6);
	}

	.empty {
		margin-top: 2rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.toggle-label {
		white-space: nowrap;
	}

	.old {
		margin-bottom: 1rem;
		overflow-wrap: anywhere;
	}

	h5 {
		margin: 1rem 0 0.25rem;
	}

	.preview {
		margin-top: 0.75rem;
	}

	.preview li {
		margin-bottom: 0.25rem;
	}

	.ok {
		margin-top: 0.75rem;
		color: var(--cds-support-02, #42be65);
	}
</style>
