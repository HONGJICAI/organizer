<script lang="ts">
	import { ComicsService } from '$lib/client';
	import { Comic, ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { page } from '$app/state';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		Checkbox,
		ContentSwitcher,
		InlineLoading,
		Modal,
		Slider,
		Switch,
		Tag,
		Tile,
		Toggle
	} from 'carbon-components-svelte';
	import { Checkmark, Copy, Erase, Grid, Home, Renew, TrashCan } from 'carbon-icons-svelte';
	import {
		clearGroup,
		filterGroups,
		keepOnly,
		pageMismatch,
		groupSize,
		selectedIn,
		sortBySize,
		suggestedSelection,
		type DupFilter
	} from '$lib/duplicateSelection';

	interface Group {
		exact: boolean;
		keepId: number;
		items: Comic[];
	}

	let mediaType = $derived(page.params.mediaType);
	let loading = $state(true);
	let groups = $state<Group[]>([]);
	// Similarity threshold in percent; the API takes 0.5–1.0.
	let threshold = $state(85);
	// Default to dropping the record too: a duplicate copy rarely needs an
	// archived tombstone ("Archive record" keeps one).
	let permanent = $state(true);
	let selected = $state<Set<number>>(new Set());
	let confirmOpen = $state(false);
	let deleting = $state(false);

	const filters: DupFilter[] = ['all', 'exact', 'similar'];
	let filterIndex = $state(0);
	// Selections in hidden groups are kept (they come back with the filter) but
	// never counted or deleted: every action works on what is on screen.
	let visible = $derived(sortBySize(filterGroups(groups, filters[filterIndex])));
	let visibleSelected = $derived(selectedIn(selected, visible));
	let selectedCount = $derived(visibleSelected.length);
	let selectedSize = $derived(
		visible.flatMap((g) => g.items).reduce((n, c) => (selected.has(c.id) ? n + c.size : n), 0)
	);
	let duplicateCount = $derived(visible.reduce((n, g) => n + g.items.length - 1, 0));
	let totalSize = $derived(visible.reduce((n, g) => n + groupSize(g), 0));
	let exactCount = $derived(groups.filter((g) => g.exact).length);

	// Comic.size is MB.
	function formatSize(mb: number) {
		return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(mb >= 100 ? 0 : 1)} MB`;
	}

	async function load() {
		loading = true;
		const { data, error } = await ComicsService.comicFindDuplicates({
			query: { threshold: threshold / 100 }
		});
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to find duplicates' }));
			groups = [];
		} else {
			groups = data.groups.map((g) => ({
				exact: g.exact,
				keepId: g.keepId,
				items: g.items.map((c) => new Comic(c))
			}));
		}
		// Nothing is pre-selected; "Select suggested" applies the Keep hints.
		selected = new Set();
		loading = false;
	}

	function toggle(id: number, checked: boolean) {
		const next = new Set(selected);
		if (checked) next.add(id);
		else next.delete(id);
		selected = next;
	}

	// Deleting every copy of a work is almost certainly a mistake, so flag
	// groups where nothing would be left.
	let wipedGroups = $derived(
		visible.filter((g) => g.items.every((c) => selected.has(c.id))).length
	);

	async function copyName(name: string) {
		try {
			await navigator.clipboard.writeText(name);
			addNotification(new SuccessNotification({ subtitle: 'Name copied' }));
		} catch {
			addNotification(new ErrorNotification({ subtitle: 'Copy failed' }));
		}
	}

	function folderOf(path: string) {
		const i = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
		return i > 0 ? path.slice(0, i) : '';
	}

	async function deleteSelected() {
		confirmOpen = false;
		deleting = true;
		let failed = 0;
		const deleted = new Set<number>();
		for (const id of visibleSelected) {
			const { error } = await ComicsService.comicDelete({ path: { id }, query: { permanent } });
			if (error) {
				failed++;
				addNotification(new ErrorNotification({ subtitle: `${id}: ${error?.msg}` }));
			} else {
				deleted.add(id);
			}
		}
		groups = groups
			.map((g) => ({ ...g, items: g.items.filter((c) => !deleted.has(c.id)) }))
			.filter((g) => g.items.length > 1);
		selected = new Set([...selected].filter((id) => !deleted.has(id)));
		deleting = false;
		if (deleted.size > 0) {
			refreshMediaFiles(mediaType);
			addNotification(
				new SuccessNotification({
					subtitle: `Deleted ${deleted.size}${failed ? `, ${failed} failed` : ''}`
				})
			);
		}
	}

	load();
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/{mediaType}">
		<span class="crumb"><Home size={16} /><span>{mediaType}</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Duplicates</BreadcrumbItem>
</Breadcrumb>
<h1>Duplicates</h1>
<p class="hint">
	Comics are grouped by title after stripping tags like <code>[汉化组]</code>,
	<code>(C99)</code>, <code>【DL版】</code>, the extension and width/case differences. Different
	volume numbers (<code>01</code> / <code>Vol.2</code> / <code>第三卷</code> / <code>上・下</code>)
	are never grouped. <em>Exact</em> groups reduce to the same title; <em>Similar</em> ones only pass
	the similarity threshold — check those carefully. Nothing is selected to start with; the
	<strong>Keep</strong> tag marks the suggested copy (favorited, then most pages, then largest), and
	<em>Select suggested</em> selects every other copy. Groups are sorted by their total size; counts and
	deletion only cover the groups the filter shows. Comics opened from here are read privately: their
	reading progress isn't saved unless you turn it on from the reader's header.
</p>

<div class="controls">
	<div class="slider">
		<Slider
			labelText="Similarity threshold (%)"
			min={50}
			max={100}
			step={5}
			bind:value={threshold}
			on:change={load}
		/>
	</div>
	<Toggle
		labelText="Delete mode"
		labelA="Archive record"
		labelB="Remove record"
		bind:toggled={permanent}
	/>
	<Button kind="ghost" icon={Renew} disabled={loading} on:click={load}>Refresh</Button>
	<Button
		kind="ghost"
		icon={Checkmark}
		disabled={loading || deleting}
		on:click={() => (selected = suggestedSelection(visible))}>Select suggested</Button
	>
	<Button
		kind="ghost"
		icon={Erase}
		disabled={loading || deleting || selectedCount === 0}
		on:click={() => (selected = new Set())}>Clear selection</Button
	>
	<Button
		kind="danger"
		icon={TrashCan}
		disabled={loading || deleting || selectedCount === 0}
		on:click={() => (confirmOpen = true)}>Delete selected ({selectedCount})</Button
	>
</div>

{#if loading}
	<InlineLoading description="Scanning names…" />
{:else if groups.length === 0}
	<p class="empty">No duplicates found. 🎉</p>
{:else}
	<ContentSwitcher bind:selectedIndex={filterIndex} size="sm" class="filter">
		<Switch text="All ({groups.length})" />
		<Switch text="Exact ({exactCount})" />
		<Switch text="Similar ({groups.length - exactCount})" />
	</ContentSwitcher>
	<p class="summary">
		{visible.length} groups, {duplicateCount} extra copies · {formatSize(totalSize)} in total
		{#if selectedCount > 0}· {formatSize(selectedSize)} selected{/if}
	</p>
	{#if deleting}
		<InlineLoading description="Deleting…" />
	{/if}
	{#each visible as group, gi (group.keepId)}
		<Tile class="group">
			<div class="group-header">
				<span>#{gi + 1}</span>
				{#if group.exact}
					<Tag type="green" size="sm">Exact</Tag>
				{:else}
					<Tag type="warm-gray" size="sm">Similar</Tag>
				{/if}
				{#if pageMismatch(group)}
					<Tag
						type="red"
						size="sm"
						title="Page counts differ by 1.5× or more — may be different books or an incomplete copy"
						>⚠ Page counts differ</Tag
					>
				{/if}
				<span class="saving">{formatSize(groupSize(group))}</span>
				<Button
					kind="ghost"
					size="small"
					disabled={deleting || !group.items.some((c) => selected.has(c.id))}
					on:click={() => (selected = clearGroup(selected, group))}>Keep all</Button
				>
			</div>
			<div class="items">
				{#each group.items as comic (comic.id)}
					<div class="item" class:marked={selected.has(comic.id)}>
						<a
							class="cover-cell"
							href="/{mediaType}/{comic.id}?private=1"
							target="_blank"
							rel="noopener"
							title="Open in reader"
						>
							<img
								class="cover"
								src={comic.coverUrl}
								alt={comic.name}
								loading="lazy"
								onerror={(e) => {
									(e.currentTarget as HTMLImageElement).style.visibility = 'hidden';
								}}
							/>
						</a>
						<div class="name-row">
							<Checkbox
								hideLabel
								labelText="Select {comic.name}"
								disabled={comic.favorited || deleting}
								checked={selected.has(comic.id)}
								on:change={(e) => toggle(comic.id, (e.target as HTMLInputElement).checked)}
							/>
							<span class="name"
								>{comic.name}<button
									class="copy"
									title="Copy name"
									aria-label="Copy name"
									onclick={() => copyName(comic.name)}><Copy size={16} /></button
								></span
							>
						</div>
						<div class="tags">
							{#if comic.id === group.keepId}
								<Tag type="blue" size="sm">Keep</Tag>
							{/if}
							{#if comic.favorited}
								<Tag type="magenta" size="sm">Favorited</Tag>
							{/if}
						</div>
						<div class="detail">{comic.page} pages · {formatSize(comic.size)}</div>
						<div class="detail path" title={comic.path}>{folderOf(comic.path)}</div>
						<div class="actions">
							<Button
								kind="ghost"
								size="small"
								icon={Grid}
								href="/{mediaType}/{comic.id}?overview=1&private=1"
								target="_blank"
								rel="noopener">Pages</Button
							>
							<Button
								kind="ghost"
								size="small"
								disabled={deleting}
								on:click={() => (selected = keepOnly(selected, group, comic.id))}
								>Keep only this</Button
							>
						</div>
					</div>
				{/each}
			</div>
		</Tile>
	{/each}
{/if}

<Modal
	danger
	bind:open={confirmOpen}
	modalHeading="Delete {selectedCount} comics?"
	primaryButtonText="Delete"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmOpen = false)}
	on:submit={deleteSelected}
>
	<p>
		The files will be deleted from disk. {permanent
			? 'Their records are removed too.'
			: 'Their records are kept as archived.'}
	</p>
	{#if wipedGroups > 0}
		<p class="warning">
			⚠ {wipedGroups} group(s) have every copy selected — nothing of those works will be left.
		</p>
	{/if}
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
		margin-bottom: 1rem;
	}

	.slider {
		min-width: 16rem;
	}

	.saving {
		margin-left: auto;
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	:global(.bx--content-switcher.filter) {
		max-width: 24rem;
	}

	.summary,
	.empty {
		margin: 1rem 0;
		color: var(--cds-text-02, #c6c6c6);
	}

	:global(.bx--tile.group) {
		margin-bottom: 1rem;
	}

	.group-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	/* Each card spans five rows of the group grid and adopts them via subgrid, so
	   name / tags / size / path / actions line up across cards in a visual row
	   (each row is as tall as its tallest card's content). */
	.items {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
		column-gap: 0.75rem;
		row-gap: 0.75rem;
	}

	.item {
		display: grid;
		grid-row: span 5;
		grid-template-rows: subgrid;
		grid-template-columns: 72px minmax(0, 1fr);
		column-gap: 0.75rem;
		row-gap: 0.25rem;
		padding: 0.5rem;
		border: 1px solid transparent;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.item > :not(.cover-cell) {
		grid-column: 2;
		min-width: 0;
	}

	.item.marked {
		border-color: var(--cds-support-01, #fa4d56);
	}

	.cover-cell {
		grid-column: 1;
		grid-row: 1 / -1;
		align-self: start;
		width: 72px;
		height: 108px;
		background: var(--cds-ui-03, #393939);
	}

	.cover {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.tags {
		display: flex;
		gap: 0.25rem;
	}

	.name-row {
		display: flex;
		align-items: flex-start;
		gap: 0.25rem;
	}

	/* Carbon's checkbox wrapper reserves label space; shrink it to the box. */
	.name-row :global(.bx--form-item.bx--checkbox-wrapper) {
		flex: none;
		width: auto;
	}

	.name {
		font-size: 0.875rem;
		line-height: 1.3;
		user-select: text;
	}

	/* Inline after the last word so it follows wrapped names. */
	.copy {
		display: inline-flex;
		vertical-align: text-bottom;
		margin-left: 0.25rem;
		padding: 0;
		border: none;
		background: none;
		color: var(--cds-icon-02, #8d8d8d);
		cursor: pointer;
		user-select: none;
	}

	.copy:hover,
	.copy:focus-visible {
		color: var(--cds-icon-01, #f4f4f4);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		align-self: end;
		margin-left: -0.5rem;
	}

	/* Carbon pads icon buttons for a trailing icon; tighten so both fit on one line. */
	.actions :global(.bx--btn) {
		padding-left: 0.5rem;
		padding-right: 0.5rem;
		gap: 0.25rem;
	}

	.actions :global(.bx--btn__icon) {
		position: static;
		margin-left: 0.25rem;
	}

	.detail {
		font-size: 0.75rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.path {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.warning {
		margin-top: 1rem;
		color: var(--cds-support-01, #fa4d56);
	}
</style>
