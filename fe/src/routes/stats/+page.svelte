<script lang="ts">
	import { ComicsService } from '$lib/client';
	import type { ComicStatsResponse } from '$lib/client';
	import { ErrorNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import MonthBars from '$lib/components/MonthBars.svelte';
	import { compact, formatBytes, niceBytes } from '$lib/stats';
	import {
		Breadcrumb,
		BreadcrumbItem,
		ContentSwitcher,
		InlineLoading,
		Switch,
		Tile
	} from 'carbon-components-svelte';
	import { Home } from 'carbon-icons-svelte';

	const ranges = [6, 12, 24];
	let rangeIndex = $state(1);
	let stats = $state<ComicStatsResponse | null>(null);
	let loading = $state(true);

	async function load(months: number) {
		loading = true;
		const { data, error } = await ComicsService.comicGetStats({ query: { months } });
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to load stats' }));
		} else {
			stats = data;
		}
		loading = false;
	}

	$effect(() => {
		load(ranges[rangeIndex]);
	});

	let months = $derived(stats?.months.map((m) => m.month) ?? []);

	function monthLines(i: number): string[] {
		const m = stats?.months[i];
		if (!m) return [];
		return [
			`${m.added} added`,
			`${m.read} read (${m.readDays} comic-days)`,
			`${m.deleted} deleted · ${formatBytes(m.deletedSize)} freed`
		];
	}
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/">
		<span class="crumb"><Home size={16} /><span>home</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Stats</BreadcrumbItem>
</Breadcrumb>
<h1>Comic stats</h1>

{#if !stats}
	<InlineLoading description="Loading…" />
{:else}
	{@const lib = stats.library}
	{@const total = stats.total}
	<p class="hint">
		{#if stats.since}
			Activity is logged since {new Date(stats.since).toLocaleDateString()}. The first scan after
			that logs the whole existing library as added.
		{:else}
			No activity logged yet — adds, reads and deletes are recorded from now on.
		{/if}
	</p>

	<h2>Library</h2>
	<div class="tiles">
		<Tile><span class="label">Comics</span><span class="value">{compact(lib.total)}</span></Tile>
		<Tile
			><span class="label">Size</span><span class="value">{formatBytes(lib.totalSize)}</span></Tile
		>
		<Tile><span class="label">Started</span><span class="value">{compact(lib.started)}</span></Tile>
		<Tile
			><span class="label">Finished</span><span class="value">{compact(lib.finished)}</span></Tile
		>
		<Tile
			><span class="label">Favorited</span><span class="value">{compact(lib.favorited)}</span></Tile
		>
		<Tile
			><span class="label">Archived</span><span class="value">{compact(lib.archived)}</span></Tile
		>
	</div>

	<h2>All-time activity</h2>
	<div class="tiles">
		<Tile><span class="label">Added</span><span class="value">{compact(total.added)}</span></Tile>
		<Tile><span class="label">Read</span><span class="value">{compact(total.read)}</span></Tile>
		<Tile
			><span class="label">Comic-days read</span><span class="value">{compact(total.readDays)}</span
			></Tile
		>
		<Tile
			><span class="label">Deleted</span><span class="value">{compact(total.deleted)}</span></Tile
		>
		<Tile
			><span class="label">Space freed</span><span class="value"
				>{formatBytes(total.deletedSize)}</span
			></Tile
		>
	</div>

	<div class="section-head">
		<h2>By month</h2>
		<ContentSwitcher bind:selectedIndex={rangeIndex} size="sm">
			{#each ranges as r (r)}
				<Switch text="{r} months" disabled={loading} />
			{/each}
		</ContentSwitcher>
	</div>
	<div class="charts">
		<MonthBars
			title="Comics added"
			{months}
			values={stats.months.map((m) => m.added)}
			format={compact}
			tooltip={monthLines}
		/>
		<MonthBars
			title="Comics read"
			{months}
			values={stats.months.map((m) => m.read)}
			format={compact}
			tooltip={monthLines}
		/>
		<MonthBars
			title="Space freed by deletes"
			{months}
			values={stats.months.map((m) => m.deletedSize)}
			format={formatBytes}
			tooltip={monthLines}
			nice={niceBytes}
		/>
	</div>
	<details>
		<summary>Show as table</summary>
		<table>
			<thead>
				<tr>
					<th>Month</th><th>Added</th><th>Read</th><th>Comic-days</th><th>Deleted</th><th>Freed</th>
				</tr>
			</thead>
			<tbody>
				{#each [...stats.months].reverse() as m (m.month)}
					<tr>
						<td>{m.month}</td><td>{m.added}</td><td>{m.read}</td><td>{m.readDays}</td><td
							>{m.deleted}</td
						><td>{formatBytes(m.deletedSize)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</details>

	<h2>Most read</h2>
	{#if stats.topRead.length === 0}
		<p class="hint">Nothing read yet.</p>
	{:else}
		<ol class="top">
			{#each stats.topRead as c (c.id)}
				<li>
					<a href="/comic/{c.id}">{c.name}</a>
					<span class="days">{c.readDays} {c.readDays === 1 ? 'day' : 'days'}</span>
				</li>
			{/each}
		</ol>
	{/if}
{/if}

<style>
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}

	h2 {
		margin: 2rem 0 0.75rem;
		font-size: 1.25rem;
	}

	.hint {
		max-width: 60rem;
		margin: 0.5rem 0 1rem;
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
	}

	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
		gap: 0.5rem;
	}

	.tiles :global(.bx--tile) {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		min-height: auto;
	}

	.label {
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.value {
		font-size: 1.75rem;
		font-weight: 600;
	}

	.section-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin: 2rem 0 0.75rem;
	}

	.section-head h2 {
		margin: 0;
	}

	.section-head :global(.bx--content-switcher) {
		max-width: 20rem;
	}

	.charts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 2rem;
	}

	details {
		margin-top: 1.5rem;
		font-size: 0.875rem;
	}

	summary {
		cursor: pointer;
		color: var(--cds-link-01, #78a9ff);
	}

	table {
		margin-top: 0.75rem;
		border-collapse: collapse;
		font-variant-numeric: tabular-nums;
	}

	th,
	td {
		padding: 0.25rem 1rem 0.25rem 0;
		text-align: right;
		border-bottom: 1px solid var(--cds-ui-03, #393939);
	}

	th:first-child,
	td:first-child {
		text-align: left;
	}

	.top {
		list-style: decimal inside;
		font-size: 0.875rem;
	}

	.top li {
		padding: 0.25rem 0;
	}

	.days {
		margin-left: 0.5rem;
		color: var(--cds-text-02, #c6c6c6);
	}
</style>
