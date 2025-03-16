<script lang="ts">
	import { ComicsService, type ComicEntity } from '$lib/client';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		DataTable,
		DataTableSkeleton,
		Toolbar,
		ToolbarBatchActions,
		ToolbarContent,
		ToolbarMenu,
		ToolbarMenuItem,
		ToolbarSearch
	} from 'carbon-components-svelte';
	import { TrashCan } from 'carbon-icons-svelte';
	interface Request<T> {
		loading: boolean;
		data?: T;
	}
	let fileNotFoundData = $state<Request<ComicEntity[]>>();
	let selectedRowIds = $state<number[]>([]);
	async function onClickFileNotFoundEntity() {
		fileNotFoundData = { loading: true, data: undefined };
		const { data, error } = await ComicsService.comicGetAll({
			query: {
				fileMiss: true
			}
		});
		if (error) {
			fileNotFoundData = { loading: false, data: undefined };
		} else {
			fileNotFoundData = {
				loading: false,
				data: data.filter((comic: ComicEntity) => !comic.favorited && !comic.archived)
			};
		}
	}
	async function batchDelete() {
		const ids = selectedRowIds ?? [];
		if (ids.length > 0) {
			for (const id of ids) {
				const { error } = await ComicsService.comicDelete({
					path: {
						id: id
					},
					query: {
						permanent: true
					}
				});
				if (error) {
					addNotification(new ErrorNotification({ subtitle: `${id}: ${error?.msg}` }));
					throw error;
				} else {
					fileNotFoundData?.data?.splice(
						fileNotFoundData.data.findIndex((comic) => comic.id === id),
						1
					);
				}
			}

			addNotification(new SuccessNotification({ subtitle: 'Deleted' }));
		}
	}
	onClickFileNotFoundEntity();
</script>

<Breadcrumb>
	<BreadcrumbItem href="/">Home</BreadcrumbItem>
	<BreadcrumbItem href="/comic">Comic</BreadcrumbItem>
	<BreadcrumbItem href="/comic/orgnize" isCurrentPage>Orgnize</BreadcrumbItem>
</Breadcrumb>
<h1>File Not Found Entities</h1>
<container>
	{#if fileNotFoundData?.loading ?? false}
		<DataTableSkeleton
			rows={10}
			headers={[
				{ key: 'id', value: 'Id' },
				{ key: 'name', value: 'Name' },
				{ key: 'lastViewedTime', value: 'Last Viewed Time' },
				{ key: 'favorited', value: 'Favorited' },
				{ key: 'archived', value: 'Archived' }
			]}
		/>
	{:else if (fileNotFoundData?.data?.length ?? 0) > 0}
		<DataTable
			selectable
			batchSelection
			headers={[
				{ key: 'id', value: 'Id' },
				{ key: 'name', value: 'Name' },
				{ key: 'lastViewedTime', value: 'Last Viewed Time' },
				{ key: 'favorited', value: 'Favorited' },
				{ key: 'archived', value: 'Archived' }
			]}
			rows={fileNotFoundData?.data}
			bind:selectedRowIds
		>
			<Toolbar>
				<ToolbarBatchActions>
					<Button kind="danger" icon={TrashCan} on:click={batchDelete}>Delete</Button>
				</ToolbarBatchActions>
				<ToolbarContent>
					<ToolbarSearch />
					<ToolbarMenu>
						<ToolbarMenuItem hasDivider danger>Delete all</ToolbarMenuItem>
					</ToolbarMenu>
					<Button>Refresh</Button>
				</ToolbarContent>
			</Toolbar>
		</DataTable>
	{:else}
		<p>No such entities</p>
	{/if}
</container>

<style>
	container {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 0.5rem;
	}
</style>
