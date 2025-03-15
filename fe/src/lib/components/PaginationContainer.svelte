<script lang="ts">
	import { Pagination, PaginationSkeleton } from 'carbon-components-svelte';

	interface Props {
		skeleton?: boolean;
		totalItems?: number;
		page?: number;
		pageSize?: number;
		onPaginationChange?: (page?: number, pageSize?: number) => void;
	}

	let { skeleton, totalItems, page, pageSize, onPaginationChange }: Props = $props();
	let pageSizes = [20, 25];
	const onChange = (e: CustomEvent<{ page?: number; pageSize?: number }>) => {
		onPaginationChange?.(e.detail.page, e.detail.pageSize);
	};
</script>

{#if skeleton}
	<PaginationSkeleton />
	<slot></slot>
	<PaginationSkeleton />
{:else}
	<Pagination {totalItems} {pageSizes} {page} {pageSize} on:change={onChange} />
	<slot></slot>
	<Pagination {totalItems} {pageSizes} {page} {pageSize} on:change={onChange} />
{/if}
