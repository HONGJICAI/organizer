<script lang="ts">
	import { labelEvery, monthLabel, monthTitle, niceMax } from '$lib/stats';

	// One single-series column chart over months. The title names the series,
	// so there is no legend; values live in the hover/focus tooltip and the
	// page's table view.
	interface Props {
		title: string;
		months: string[]; // YYYY-MM, oldest first
		values: number[];
		format: (n: number) => string;
		tooltip: (i: number) => string[];
		// Rounds the axis maximum; pass niceBytes for byte values.
		nice?: (max: number) => number;
	}
	let { title, months, values, format, tooltip, nice = niceMax }: Props = $props();

	let max = $derived(nice(Math.max(0, ...values)));
	let showLabel = $derived(labelEvery(months.length, 8));
	let active = $state<number | null>(null);
</script>

<figure class="chart">
	<figcaption>{title}</figcaption>
	<div class="plot">
		<div class="y-axis" aria-hidden="true">
			<span>{format(max)}</span>
			<span>0</span>
		</div>
		<div class="area" role="group" aria-label={title} onmouseleave={() => (active = null)}>
			{#each values as value, i (months[i])}
				<button
					type="button"
					class="slot"
					aria-label="{months[i]}: {format(value)}"
					onmouseenter={() => (active = i)}
					onfocus={() => (active = i)}
					onblur={() => (active = null)}
				>
					<span class="bar" style:height="{(value / max) * 100}%"></span>
				</button>
			{/each}
			{#if active !== null}
				<div
					class="tooltip"
					class:flip={active > months.length / 2}
					style:left="{((active + 0.5) / months.length) * 100}%"
				>
					<strong>{monthTitle(months[active])}</strong>
					{#each tooltip(active) as line (line)}
						<span>{line}</span>
					{/each}
				</div>
			{/if}
		</div>
		<div class="x-axis" aria-hidden="true">
			{#each months as month, i (month)}
				<span
					>{#if showLabel(i)}{monthLabel(month, i === 0 || month.endsWith('-01'))}{/if}</span
				>
			{/each}
		</div>
	</div>
</figure>

<style>
	.chart {
		--bar: #4589ff;
		--grid: #393939;
		margin: 0;
		min-width: 0;
		/* Room for the last month label, which centers past the plot's edge. */
		padding-right: 1rem;
	}

	figcaption {
		margin-bottom: 0.75rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--cds-text-01, #f4f4f4);
	}

	.plot {
		display: grid;
		grid-template-columns: auto 1fr;
		grid-template-rows: 10rem auto;
		column-gap: 0.5rem;
	}

	.y-axis,
	.x-axis {
		font-size: 0.75rem;
		color: var(--cds-text-02, #c6c6c6);
		font-variant-numeric: tabular-nums;
	}

	.y-axis {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		align-items: flex-end;
		/* Center the tick labels on the gridline and the baseline. */
		margin: -0.5rem 0;
	}

	.area {
		position: relative;
		display: flex;
		align-items: stretch;
		border-top: 1px solid var(--grid);
		border-bottom: 1px solid var(--grid);
	}

	/* The whole column slot is the hit target, wider than the bar it holds. */
	.slot {
		flex: 1;
		display: flex;
		align-items: flex-end;
		justify-content: center;
		min-width: 0;
		padding: 0 1px;
		border: none;
		background: none;
		cursor: default;
	}

	.slot:hover,
	.slot:focus-visible {
		background: rgba(255, 255, 255, 0.05);
		outline: none;
	}

	.bar {
		width: 100%;
		max-width: 24px;
		background: var(--bar);
		border-radius: 4px 4px 0 0;
	}

	.tooltip {
		position: absolute;
		top: 0;
		transform: translateX(0.5rem);
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		padding: 0.5rem 0.75rem;
		background: var(--cds-ui-01, #262626);
		border: 1px solid var(--grid);
		font-size: 0.75rem;
		white-space: nowrap;
		pointer-events: none;
		z-index: 1;
	}

	.tooltip.flip {
		transform: translateX(calc(-100% - 0.5rem));
	}

	.x-axis {
		grid-column: 2;
		display: flex;
		margin-top: 0.25rem;
	}

	.x-axis span {
		flex: 1;
		min-width: 0;
		text-align: center;
		white-space: nowrap;
		overflow: visible;
	}
</style>
