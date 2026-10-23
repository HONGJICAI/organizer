<script lang="ts">
	import { adapterFor } from '$lib/mediaAdapters';
	import type { MediaFile } from '$lib/model.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { invalidate } from '$app/navigation';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { checkName } from '$lib/nameCheck';
	import {
		narrowWidth,
		normalizeName,
		ruleLabels,
		rules,
		type NormalizeRule
	} from '$lib/normalizeName';
	import { loadTags, tagState } from '$lib/tags.svelte';
	import {
		Button,
		Checkbox,
		DataTable,
		DataTableSkeleton,
		Dropdown,
		Modal,
		Pagination,
		ProgressBar,
		Tag,
		Toolbar,
		ToolbarBatchActions,
		ToolbarContent,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { Edit } from 'carbon-icons-svelte';

	// Comic names normalized in bulk (Cleanup → Normalize): full-width letters
	// and brackets to half-width, spaces tidied, language tags last. Names with
	// bracket problems are included, since narrowing often fixes them; a rename
	// that would add a problem is held back for Bad names.

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
	loadTags();

	let renamed = $state<Record<number, string>>({});
	let use = $state<Record<NormalizeRule, boolean>>({
		width: true,
		brackets: true,
		kana: true,
		spaces: true,
		language: true
	});
	type Show = 'all' | 'fixes' | 'blocked';
	let show = $state<Show>('all');
	let search = $state('');
	let pageNo = $state(1);
	let pageSize = $state(50);
	let selectedRowIds = $state<number[]>([]);

	// Language tags as classified on the Tags page, matched after narrowing.
	const languages = $derived(
		new Set(tagState.index.withKind('language').flatMap((n) => [n, narrowWidth(n)]))
	);
	const serious = (name: string) => checkName(name).filter((p) => p.kind !== 'untagged');

	type Status = 'ready' | 'fixes' | 'still' | 'blocked';
	const statusTag: Record<Status, { type: 'green' | 'teal' | 'warm-gray' | 'red'; label: string }> =
		{
			ready: { type: 'green', label: 'Ready' },
			fixes: { type: 'teal', label: 'Fixes bad name' },
			still: { type: 'warm-gray', label: 'Still a bad name' },
			blocked: { type: 'red', label: 'Would break' }
		};

	const all = $derived.by(() => {
		const on = new Set(rules.filter((r) => use[r]));
		const isLanguage = (tag: string) => languages.has(tag);
		return list
			.filter((f) => !f.archived)
			.flatMap((f) => {
				const name = renamed[f.id] ?? f.name;
				const { name: next, changed } = normalizeName(name, on, isLanguage);
				if (!changed.length) return [];
				const before = serious(name);
				const after = serious(next);
				const beforeKinds = new Set(before.map((p) => p.kind));
				const status: Status =
					after.length > before.length || after.some((p) => !beforeKinds.has(p.kind))
						? 'blocked'
						: !after.length
							? before.length
								? 'fixes'
								: 'ready'
							: 'still';
				const reason = status === 'blocked' ? after[0]?.message : undefined;
				return [{ id: f.id, name, next, changed, status, reason }];
			});
	});
	type Row = (typeof all)[number];
	const blockedIds = $derived(all.filter((r) => r.status === 'blocked').map((r) => r.id));
	const rows = $derived(
		all.filter(
			(r) =>
				(show === 'all' || (show === 'fixes' ? r.status === 'fixes' : r.status === 'blocked')) &&
				r.name.toLowerCase().includes(search.trim().toLowerCase())
		)
	);
	const shows = $derived([
		{ id: 'all', text: `All changes (${all.length})` },
		{ id: 'fixes', text: `Fixes bad names (${all.filter((r) => r.status === 'fixes').length})` },
		{ id: 'blocked', text: `Would break (${blockedIds.length})` }
	]);
	$effect(() => {
		void show;
		void search;
		void use.width;
		void use.brackets;
		void use.kana;
		void use.spaces;
		void use.language;
		pageNo = 1;
	});
	// Selections only make sense for the names as they are now.
	$effect(() => {
		const ok = new Set(all.filter((r) => r.status !== 'blocked').map((r) => r.id));
		if (selectedRowIds.some((id) => !ok.has(id)))
			selectedRowIds = selectedRowIds.filter((id) => ok.has(id));
	});

	/** The changed middle of ``b`` against ``a``, for highlighting. */
	function diff(a: string, b: string) {
		let start = 0;
		while (start < a.length && start < b.length && a[start] === b[start]) start++;
		let end = 0;
		while (
			end < a.length - start &&
			end < b.length - start &&
			a[a.length - 1 - end] === b[b.length - 1 - end]
		)
			end++;
		return {
			before: b.slice(0, start),
			mid: b.slice(start, b.length - end),
			after: b.slice(b.length - end)
		};
	}

	// --- Renaming ---------------------------------------------------------------
	let confirmOpen = $state(false);
	let run = $state<{ done: number; total: number; failed: string[]; stopping: boolean } | null>(
		null
	);

	async function renameSelected() {
		confirmOpen = false;
		const adapter = adapterFor(mediaType);
		if (!adapter?.rename) return;
		const todo = all.filter((r) => selectedRowIds.includes(r.id) && r.status !== 'blocked');
		run = { done: 0, total: todo.length, failed: [], stopping: false };
		for (const r of todo) {
			if (run.stopping) break;
			const { error } = await adapter.rename(r.id, r.next);
			if (error !== undefined) run.failed.push(`${r.name}: ${error}`);
			else renamed[r.id] = r.next;
			run.done++;
		}
		const ok = run.done - run.failed.length;
		selectedRowIds = [];
		if (ok) {
			// Reload the list, so the other tabs see the new names too.
			refreshMediaFiles(mediaType);
			invalidate(`app:media:${mediaType}`);
		}
		addNotification(
			run.failed.length
				? new ErrorNotification({
						subtitle: `Renamed ${ok} of ${run.done}; ${run.failed.length} failed`
					})
				: new SuccessNotification({ subtitle: `Renamed ${ok} comic(s)` })
		);
		const failed = run.failed;
		run = null;
		lastFailures = failed;
	}
	let lastFailures = $state<string[]>([]);
</script>

<p class="hint">
	Renames comics to a consistent form: full-width letters, digits and symbols to half-width (<code
		>Ａｕｔｈｏｒ</code
	>
	→ <code>Author</code>), full-width brackets to half-width so they read as tags (<code
		>（C99）</code
	>
	→ <code>(C99)</code>; 【】 and 《》 stay), half-width katakana to full-width, single spaces, and
	tags marked <em>language</em> on the Tags page moved to the end. Names with bracket problems are included:
	narrowing often fixes them. A rename that would add a problem is held back; fix those under Bad names.
	Renaming changes the file on disk and keeps favorite and progress.
</p>

<div class="rules">
	{#each rules as rule (rule)}
		<Checkbox labelText={ruleLabels[rule]} bind:checked={use[rule]} />
	{/each}
</div>

{#if !loaded}
	<DataTableSkeleton
		rows={10}
		headers={[
			{ key: 'name', value: 'Name' },
			{ key: 'next', value: 'Becomes' },
			{ key: 'changed', value: 'Changes' },
			{ key: 'status', value: 'Status' }
		]}
	/>
{:else}
	<div class="table">
		<DataTable
			selectable
			batchSelection
			nonSelectableRowIds={blockedIds}
			bind:selectedRowIds
			page={pageNo}
			{pageSize}
			headers={[
				{ key: 'name', value: 'Name' },
				{ key: 'next', value: 'Becomes' },
				{ key: 'changed', value: 'Changes' },
				{ key: 'status', value: 'Status' }
			]}
			{rows}
		>
			<svelte:fragment slot="cell" let:row let:cell>
				{#if cell.key === 'name'}
					<span class="name">{row.name}</span>
				{:else if cell.key === 'next'}
					{@const d = diff(row.name, row.next)}
					<span class="name">{d.before}<mark>{d.mid}</mark>{d.after}</span>
				{:else if cell.key === 'changed'}
					<span class="tags">
						{#each (row as Row).changed as rule (rule)}
							<Tag size="sm" type="outline">{ruleLabels[rule]}</Tag>
						{/each}
					</span>
				{:else if cell.key === 'status'}
					{@const st = statusTag[(row as Row).status]}
					<Tag size="sm" type={st.type} title={row.reason ?? ''}>{st.label}</Tag>
					{#if row.reason}<span class="err">{row.reason}</span>{/if}
				{/if}
			</svelte:fragment>
			<Toolbar>
				<ToolbarBatchActions>
					<Button icon={Edit} disabled={run !== null} on:click={() => (confirmOpen = true)}>
						Rename {selectedRowIds.length}
					</Button>
				</ToolbarBatchActions>
				<ToolbarContent>
					<ToolbarSearch bind:value={search} placeholder="Search names" />
					<Dropdown
						size="sm"
						type="inline"
						items={shows}
						selectedId={show}
						on:select={(e) => (show = e.detail.selectedId as Show)}
					/>
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
			{all.length ? 'Nothing matches.' : 'Every comic name is already normalized. 🎉'}
		</p>
	{/if}
	{#if lastFailures.length}
		<h4>Not renamed</h4>
		<ul class="failures">
			{#each lastFailures as f, i (i)}<li class="err">{f}</li>{/each}
		</ul>
	{/if}
{/if}

<Modal
	open={confirmOpen}
	modalHeading="Rename {selectedRowIds.length} comic(s)?"
	primaryButtonText="Rename"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmOpen = false)}
	on:close={() => (confirmOpen = false)}
	on:submit={renameSelected}
>
	<p>
		Each file is renamed on disk to the name shown under <em>Becomes</em>. Comics keep their id,
		favorite and progress. A name already taken in the same folder is skipped.
	</p>
</Modal>

<Modal
	open={run !== null}
	passiveModal
	preventCloseOnClickOutside
	modalHeading="Renaming…"
	on:close={() => run && (run.stopping = true)}
>
	{#if run}
		<ProgressBar value={run.done} max={run.total} labelText={`${run.done} / ${run.total}`} />
		{#if run.failed.length}<p class="err">{run.failed.length} failed so far</p>{/if}
		<div class="stop">
			<Button
				kind="secondary"
				size="small"
				disabled={run.stopping}
				on:click={() => run && (run.stopping = true)}>{run.stopping ? 'Stopping…' : 'Stop'}</Button
			>
		</div>
	{/if}
</Modal>

<style>
	.hint {
		max-width: 60rem;
		margin: 0.5rem 0 1rem;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
	}

	.rules {
		display: flex;
		flex-wrap: wrap;
		gap: 0 1.5rem;
		margin-bottom: 1rem;
	}

	.rules :global(.bx--form-item) {
		flex: none;
		margin: 0;
	}

	.name {
		overflow-wrap: anywhere;
	}

	mark {
		background: var(--cds-support-04, #4589ff);
		color: var(--cds-text-on-color, #fff);
		border-radius: 2px;
	}

	.tags {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.tags :global(.bx--tag),
	.table :global(td .bx--tag) {
		white-space: nowrap;
	}

	.err {
		display: block;
		color: var(--cds-text-error, #ff8389);
		font-size: 0.75rem;
	}

	.empty {
		margin-top: 2rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.failures {
		margin-top: 0.5rem;
	}

	.stop {
		margin-top: 1rem;
	}

	/* On a phone the new name says what changes. */
	@media (max-width: 671px) {
		.table :global(th:nth-child(4)),
		.table :global(td:nth-child(4)) {
			display: none;
		}
	}
</style>
