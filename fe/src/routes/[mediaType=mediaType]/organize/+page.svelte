<script lang="ts">
	import { ComicsService } from '$lib/client';
	import { Comic, ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { page } from '$app/state';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		DataTable,
		DataTableSkeleton,
		Tag,
		Toolbar,
		ToolbarBatchActions,
		ToolbarContent,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { Home, Renew, Search, TrashCan } from 'carbon-icons-svelte';

	interface Row {
		id: number;
		name: string;
		lastViewedTime: string | null;
		coverUrl: string;
	}

	let mediaType = $derived(page.params.mediaType);
	let loading = $state(true);
	let rows = $state<Row[]>([]);
	let selectedRowIds = $state<number[]>([]);
	let deleting = $state(false);
	let checking = $state(false);
	// Rows the disk check couldn't classify (a transient mount blip). They stay
	// listed but are locked out of deletion — confirming them gone is exactly
	// what we can't do when the share is flaky.
	let unverifiedIds = $state<number[]>([]);

	async function load() {
		loading = true;
		unverifiedIds = [];
		const { data, error } = await ComicsService.comicGetAll({ query: { fileMiss: true } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to load missing files' }));
			rows = [];
		} else {
			// Favorited comics are blocked from deletion by the backend, and
			// archived ones are intentional "deleted file, kept record" tombstones
			// — neither belongs in this cleanup list.
			rows = data
				.filter((c) => !c.favorited && !c.archived)
				.map((c) => {
					const comic = new Comic(c);
					return {
						id: comic.id,
						name: comic.name,
						lastViewedTime: comic.lastViewedTime,
						coverUrl: comic.coverUrl
					};
				});
		}
		selectedRowIds = [];
		loading = false;
	}

	async function checkFiles() {
		if (rows.length === 0) return;
		checking = true;
		const ids = rows.map((r) => r.id);
		const { data, error } = await ComicsService.comicCheck({ body: { ids } });
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to check files' }));
			checking = false;
			return;
		}
		const status = new Map(data.results.map((r) => [r.id, r.status]));
		let recovered = 0;
		let stillMissing = 0;
		const unknown: number[] = [];
		// `present` (file came back) and `notfound` (record already gone) both
		// drop off this cleanup list; `absent` stays and is deletable; `unknown`
		// stays but gets locked from selection below.
		rows = rows.filter((r) => {
			const s = status.get(r.id);
			if (s === 'present' || s === 'notfound') {
				recovered++;
				return false;
			}
			if (s === 'unknown') unknown.push(r.id);
			else stillMissing++;
			return true;
		});
		unverifiedIds = unknown;
		selectedRowIds = selectedRowIds.filter((id) => !unknown.includes(id));
		checking = false;
		addNotification(
			new SuccessNotification({
				subtitle: `${recovered} recovered, ${unknown.length} unverified, ${stillMissing} still missing`
			})
		);
	}

	async function deleteIds(ids: number[]) {
		if (ids.length === 0) return;
		deleting = true;
		let failed = 0;
		for (const id of ids) {
			const { error } = await ComicsService.comicDelete({
				path: { id },
				query: { permanent: true }
			});
			if (error) {
				failed++;
				addNotification(new ErrorNotification({ subtitle: `${id}: ${error?.msg}` }));
			} else {
				rows = rows.filter((r) => r.id !== id);
			}
		}
		selectedRowIds = [];
		deleting = false;
		if (failed < ids.length) {
			addNotification(new SuccessNotification({ subtitle: 'Deleted' }));
		}
	}

	load();
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/{mediaType}">
		<span class="crumb"><Home size={16} /><span>{mediaType}</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Organize</BreadcrumbItem>
</Breadcrumb>
<h1>Missing Files</h1>
<p class="hint">
	These comics still have a record but their file is gone from disk. A removable or network drive
	that's simply unmounted will reappear on the next scan — only delete records you're sure won't
	come back. Use <strong>Check files</strong> to re-probe disk now: recovered files drop off the
	list, and ones we couldn't verify (a flaky share) are marked <em>Unverified</em> and locked from deletion.
</p>

{#if loading}
	<DataTableSkeleton
		rows={10}
		headers={[
			{ key: 'coverUrl', value: 'Cover' },
			{ key: 'id', value: 'Id' },
			{ key: 'name', value: 'Name' },
			{ key: 'lastViewedTime', value: 'Last Viewed Time' }
		]}
	/>
{:else if rows.length > 0}
	<DataTable
		selectable
		batchSelection
		nonSelectableRowIds={unverifiedIds}
		headers={[
			{ key: 'coverUrl', value: 'Cover' },
			{ key: 'id', value: 'Id' },
			{ key: 'name', value: 'Name' },
			{ key: 'lastViewedTime', value: 'Last Viewed Time' }
		]}
		{rows}
		bind:selectedRowIds
	>
		<svelte:fragment slot="cell" let:row let:cell>
			{#if cell.key === 'coverUrl'}
				<div class="cover-cell">
					<img
						class="cover"
						src={row.coverUrl}
						alt={row.name}
						loading="lazy"
						onerror={(e) => {
							const t = e.currentTarget as HTMLImageElement;
							t.style.display = 'none';
							t.parentElement?.classList.add('no-cover');
						}}
					/>
				</div>
			{:else if cell.key === 'lastViewedTime'}
				{cell.value ?? '—'}
			{:else if cell.key === 'name'}
				<span class="name-cell">
					{cell.value}
					{#if unverifiedIds.includes(row.id)}
						<Tag type="warm-gray" size="sm">Unverified</Tag>
					{/if}
				</span>
			{:else}
				{cell.value}
			{/if}
		</svelte:fragment>
		<Toolbar>
			<ToolbarBatchActions>
				<Button
					kind="danger"
					icon={TrashCan}
					disabled={deleting}
					on:click={() => deleteIds(selectedRowIds)}>Delete</Button
				>
			</ToolbarBatchActions>
			<ToolbarContent>
				<ToolbarSearch />
				<Button kind="ghost" icon={Search} disabled={checking || loading} on:click={checkFiles}
					>Check files</Button
				>
				<Button kind="ghost" icon={Renew} disabled={loading} on:click={load}>Refresh</Button>
			</ToolbarContent>
		</Toolbar>
	</DataTable>
{:else}
	<p class="empty">No missing files. Everything's accounted for. 🎉</p>
{/if}

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

	.empty {
		margin-top: 2rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.name-cell {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.cover-cell {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 60px;
		height: 90px;
		background: var(--cds-ui-03, #393939);
	}

	.cover {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	/* `no-cover` is added imperatively in the img onerror handler, so the
	   compiler can't see it statically — scope it globally like FileCard does. */
	:global(.cover-cell.no-cover::after) {
		content: '?';
		font-size: 1.5rem;
		color: var(--cds-text-03, #6f6f6f);
	}
</style>
