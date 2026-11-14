<script lang="ts">
	// One row of list controls: sort key, sort direction, and optional
	// checkboxes (unread only, include subfolders). Shared by the media lists and
	// the folder page. Values come in as props and changes go out through
	// callbacks, so a list that only offers one key (Recent, Archive) can show it
	// without overwriting the key chosen for the others.
	import { Checkbox, Select, SelectItem } from 'carbon-components-svelte';
	import { SortAscending, SortDescending } from 'carbon-icons-svelte';

	interface Props {
		options: { value: number; text: string }[];
		orderBy: number;
		reverse: boolean;
		onOrderBy: (value: number) => void;
		onReverse: (reverse: boolean) => void;
		// Checkboxes after the sort controls; omit the list to show none.
		checks?: { label: string; checked: boolean; onChange: (checked: boolean) => void }[];
	}
	let { options, orderBy, reverse, onOrderBy, onReverse, checks = [] }: Props = $props();
</script>

<div class="sort-bar">
	<div class="sort">
		<Select
			size="sm"
			inline
			labelText="Sort"
			selected={orderBy}
			on:change={(e) => onOrderBy(Number((e.target as HTMLSelectElement).value))}
		>
			{#each options as { value, text } (value)}
				<SelectItem {value} {text} />
			{/each}
		</Select>
		<button
			class="direction"
			type="button"
			title={reverse ? 'Descending (click for ascending)' : 'Ascending (click for descending)'}
			aria-label={reverse ? 'Sorted descending' : 'Sorted ascending'}
			onclick={() => onReverse(!reverse)}
		>
			{#if reverse}<SortDescending size={16} />{:else}<SortAscending size={16} />{/if}
		</button>
	</div>
	{#each checks as check (check.label)}
		<Checkbox
			labelText={check.label}
			checked={check.checked}
			on:change={(e) => check.onChange((e.target as HTMLInputElement).checked)}
		/>
	{/each}
</div>

<style>
	.sort-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 1.5rem;
		padding: 0.5rem 0;
	}

	.sort {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
	}

	.sort-bar :global(.bx--form-item),
	.sort-bar :global(.bx--checkbox-wrapper) {
		flex: none;
		margin: 0;
	}

	.direction {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		padding: 0;
		border: none;
		background: none;
		color: var(--cds-icon-01, #f4f4f4);
		cursor: pointer;
	}

	.direction:hover {
		background: var(--cds-hover-ui, #353535);
	}

	.direction:focus-visible {
		outline: 2px solid var(--cds-focus, #ffffff);
		outline-offset: -2px;
	}
</style>
