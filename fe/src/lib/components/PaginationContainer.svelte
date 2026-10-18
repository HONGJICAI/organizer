<script lang="ts">
	import { Pagination, PaginationSkeleton } from 'carbon-components-svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		skeleton?: boolean;
		totalItems?: number;
		page?: number;
		pageSize?: number;
		onPaginationChange?: (page?: number, pageSize?: number) => void;
		children?: Snippet;
	}

	let { skeleton, totalItems, page, pageSize, onPaginationChange, children }: Props = $props();
	let pageSizes = [20, 25];
	// Nothing to page through when everything fits on the smallest page: the
	// bars would just be empty chrome (worst on a phone, where only the arrows
	// show).
	let showBars = $derived(totalItems === undefined || totalItems > Math.min(...pageSizes));
	const onChange = (e: CustomEvent<{ page?: number; pageSize?: number }>) => {
		onPaginationChange?.(e.detail.page, e.detail.pageSize);
	};
</script>

{#if skeleton}
	<PaginationSkeleton />
	{@render children?.()}
	<PaginationSkeleton />
{:else}
	{#if showBars}
		<Pagination {totalItems} {pageSizes} {page} {pageSize} on:change={onChange} />
	{/if}
	{@render children?.()}
	{#if showBars}
		<Pagination {totalItems} {pageSizes} {page} {pageSize} on:change={onChange} />
	{/if}
{/if}
