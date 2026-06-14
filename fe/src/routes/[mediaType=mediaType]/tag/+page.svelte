<script lang="ts">
	import { goto } from '$app/navigation';
	import { MediaType, type MediaFile } from '$lib/model.svelte';
	import { separateFilename } from '$lib/utility';
	import { NumberInput, SkeletonPlaceholder, Tag } from 'carbon-components-svelte';

	let { data } = $props();
	let dataLoaded = $state(false);
	let files = $state([] as MediaFile[]);
	$effect(() => {
		const pending = data.files;
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

	interface TagDetail {
		tag: string;
		count: number;
		archiveCount: number;
		favoriteCount: number;
		viewCount: number;
	}

	// How many tags each ranking shows.
	const topN = 20;
	// Tags below this many files are excluded from the rate rankings so a tag
	// with a handful of items can't dominate a percentage chart. Adjustable.
	let minCount = $state(5);

	let mediaType = $derived(files[0]?.type);
	// Match the main list: comics tag off their name, everything else off path.
	const tagsOf = (f: MediaFile) =>
		separateFilename(mediaType === MediaType.Comic ? f.name : f.path);

	let tagDetails = $derived.by(() => {
		const tag2detail = new Map<string, TagDetail>();
		files.forEach((f) => {
			tagsOf(f).forEach((tag) => {
				const d = tag2detail.get(tag) ?? {
					tag,
					count: 0,
					archiveCount: 0,
					favoriteCount: 0,
					viewCount: 0
				};
				d.count++;
				if (f.archived) d.archiveCount++;
				if (f.favorited) d.favoriteCount++;
				if (f.viewed) d.viewCount++;
				tag2detail.set(tag, d);
			});
		});
		return Array.from(tag2detail.values());
	});

	let totalTags = $derived(tagDetails.length);
	// Pool that rate rankings rank over.
	let qualified = $derived(tagDetails.filter((d) => d.count >= minCount));

	let topByCount = $derived(
		tagDetails
			.slice()
			.sort((a, b) => b.count - a.count)
			.slice(0, topN)
	);
	let topByViewRate = $derived(
		qualified
			.slice()
			.sort((a, b) => b.viewCount / b.count - a.viewCount / a.count)
			.slice(0, topN)
	);
	let topByFavoriteRate = $derived(
		qualified
			.slice()
			.sort((a, b) => b.favoriteCount / b.count - a.favoriteCount / a.count)
			.slice(0, topN)
	);
	let topByArchiveRate = $derived(
		qualified
			.slice()
			.sort((a, b) => b.archiveCount / b.count - a.archiveCount / a.count)
			.slice(0, topN)
	);

	const pct = (n: number, total: number) => (total === 0 ? 0 : Math.round((n / total) * 100));
	const onTagClick = (tag: string) => goto(`/${data.mediaType}?q=${encodeURIComponent(tag)}`);
</script>

{#snippet rateRanking(title: string, items: TagDetail[], pick: (d: TagDetail) => number)}
	<section class="panel">
		<h3>{title}</h3>
		{#if items.length === 0}
			<p class="empty">No tag has at least {minCount} items.</p>
		{:else}
			<div class="chips">
				{#each items as d (d.tag)}
					<Tag interactive on:click={() => onTagClick(d.tag)}>
						<div class="chip">
							<span class="name" title={d.tag}>{d.tag}</span>
							<span class="metric">{pct(pick(d), d.count)}% · {pick(d)}/{d.count}</span>
						</div>
					</Tag>
				{/each}
			</div>
		{/if}
	</section>
{/snippet}

<div class="layout">
	<div class="header">
		<h2>Tags</h2>
		<div class="control">
			<NumberInput size="sm" label="Min items for rate rankings" min={1} bind:value={minCount} />
		</div>
	</div>

	{#if !dataLoaded}
		<div class="grid">
			{#each Array(4) as _}
				<SkeletonPlaceholder style="width: 100%; height: 16rem" />
			{/each}
		</div>
	{:else if totalTags === 0}
		<div class="empty-state">
			<p>No tags found</p>
			<p class="empty-hint">Tags are derived from file names — nothing to show yet.</p>
		</div>
	{:else}
		<div class="grid">
			<section class="panel">
				<h3>Most common</h3>
				<div class="chips">
					{#each topByCount as d (d.tag)}
						<Tag interactive on:click={() => onTagClick(d.tag)}>
							<div class="chip">
								<span class="name" title={d.tag}>{d.tag}</span>
								<span class="metric">{d.count}</span>
							</div>
						</Tag>
					{/each}
				</div>
			</section>
			{@render rateRanking('Most viewed', topByViewRate, (d) => d.viewCount)}
			{@render rateRanking('Most favorited', topByFavoriteRate, (d) => d.favoriteCount)}
			{@render rateRanking('Most archived', topByArchiveRate, (d) => d.archiveCount)}
		</div>
	{/if}
</div>

<style>
	.layout {
		padding: 0.5rem;
	}
	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.header h2 {
		margin: 0;
	}
	.control {
		width: 14rem;
		max-width: 100%;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1rem;
		align-items: start;
	}
	.panel {
		background: var(--cds-ui-01, #262626);
		border-radius: 0.25rem;
		padding: 1rem;
	}
	.panel h3 {
		margin: 0 0 0.75rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--cds-text-02, #c6c6c6);
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	.chip {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		max-width: 16rem;
	}
	.name {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.metric {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-02, #c6c6c6);
	}
	.empty {
		font-size: 0.8125rem;
		color: var(--cds-text-03, #8d8d8d);
		margin: 0;
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
		font-size: 0.875rem;
		margin-top: 0.5rem;
		color: var(--cds-text-03, #8d8d8d);
	}
</style>
