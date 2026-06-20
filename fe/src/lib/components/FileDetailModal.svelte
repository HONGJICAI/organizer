<script lang="ts">
	import {
		Button,
		Checkbox,
		ComposedModal,
		CopyButton,
		DataTable,
		InlineLoading,
		Modal,
		ModalBody,
		ModalFooter,
		ModalHeader,
		Tag,
		TextArea,
		TextInput
	} from 'carbon-components-svelte';
	import {
		Comic,
		MediaType,
		type MediaFile,
		Video,
		SuccessNotification,
		ErrorNotification
	} from '$lib/model.svelte';
	import { separateFilename } from '$lib/utility';
	import {
		ApplicationWeb,
		Book,
		Edit,
		Favorite,
		FavoriteFilled,
		NewTab,
		Save,
		Search as SearchIcon,
		TrashCan,
		UpdateNow
	} from 'carbon-icons-svelte';
	import { ComicsService, ImagesService, VideosService } from '$lib/client';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { goto } from '$app/navigation';

	interface Props {
		open?: boolean;
		onCloseModal?: () => void;
		file: MediaFile;
		onClickTag?: (tag: string) => void;
		onClickPrimaryButton?: () => void;
		onFileDeleted?: (permenant: boolean) => void;
	}

	let {
		open = $bindable(false),
		onCloseModal = () => undefined,
		file = $bindable(),
		onClickTag = () => undefined,
		onClickPrimaryButton = () => undefined,
		onFileDeleted = () => undefined
	}: Props = $props();
	let mediaType = $derived(file.type);
	let comicfile = $derived(file.type === MediaType.Comic ? (file as Comic) : null);
	let videofile = $derived(file.type === MediaType.Video ? (file as Video) : null);
	let separateToTagsFrom = $derived(file.type === MediaType.Comic ? file.name : file.path);
	let permanent = $state(false);
	let openDeleteModal = $state(false);
	let sendingDelete = $state(false);
	async function onClickDelete() {
		sendingDelete = true;
		openDeleteModal = false;
		const requestData = {
			path: {
				id: file.id
			},
			query: {
				permanent
			}
		};
		switch (mediaType) {
			case MediaType.Comic: {
				const { error } = await ComicsService.comicDelete(requestData);
				if (error) {
					addNotification(new ErrorNotification({ subtitle: error?.msg }));
				} else {
					onFileDeleted(permanent);
					// The per-type list is cached for the session (see mediaStore); drop it
					// so navigating away and back re-fetches instead of resurrecting the
					// just-deleted/archived file from stale cache.
					refreshMediaFiles(mediaType);
					onCloseModal();
				}
				break;
			}
			case MediaType.Video: {
				const { error } = await VideosService.videoDelete(requestData);
				if (error) {
					addNotification(new ErrorNotification({ subtitle: error?.msg }));
				} else {
					onFileDeleted(permanent);
					// The per-type list is cached for the session (see mediaStore); drop it
					// so navigating away and back re-fetches instead of resurrecting the
					// just-deleted/archived file from stale cache.
					refreshMediaFiles(mediaType);
					onCloseModal();
				}
				break;
			}
			case MediaType.Image: {
				const { error } = await ImagesService.imageDelete({ path: { id: file.id } });
				if (error) {
					addNotification(new ErrorNotification({ subtitle: error?.msg }));
				} else {
					onFileDeleted(true);
					refreshMediaFiles(mediaType);
					onCloseModal();
				}
				break;
			}
			default:
				alert(`Unknown media type: ${mediaType}`);
				throw new Error(`Unknown media type: ${mediaType}`);
		}
		sendingDelete = false;
	}
	let sendingFavorite = $state(false);
	const onClickFavorite = async () => {
		if (sendingFavorite) {
			return;
		}
		sendingFavorite = true;
		const { data, error } = file.favorited
			? await ComicsService.comicUnfavor({
					path: {
						id: file.id
					}
				})
			: await ComicsService.comicFavor({
					path: {
						id: file.id
					}
				});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else {
			file.favorited = data.favorited;
		}
		sendingFavorite = false;
	};

	let sendingRefresh = $state(false);
	async function onClickRefresh() {
		sendingRefresh = true;
		const requestData = {
			path: {
				id: file.id
			}
		};
		switch (mediaType) {
			case MediaType.Comic: {
				const { data, error } = await ComicsService.comicRefresh(requestData);
				if (error) {
					addNotification(new ErrorNotification({ subtitle: error?.msg }));
				}
				if (data) {
					// update in place so the same object held by cached list views
					// reflects the refresh, instead of replacing it with a new instance
					file.update(data);
					addNotification(new SuccessNotification({ subtitle: `Refreshed ${file.name}` }));
				}
				break;
			}
			case MediaType.Image: {
				const { data, error } = await ImagesService.imageRefresh(requestData);
				if (error) {
					addNotification(new ErrorNotification({ subtitle: error?.msg }));
				}
				if (data) {
					file.update(data);
					addNotification(new SuccessNotification({ subtitle: `Refreshed ${file.name}` }));
				}
				break;
			}
		}
		sendingRefresh = false;
	}
	let editingName = $state(false);
	let newname = $state(file.name);
	let sendingRename = $state(false);
	async function onClickSaveName() {
		sendingRename = true;
		const { error } = await ComicsService.comicRename({
			body: { name: newname },
			path: {
				id: file.id
			}
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else {
			editingName = false;
			file.name = newname;
			addNotification(new SuccessNotification({ subtitle: `Renamed to ${newname}` }));
		}
		sendingRename = false;
	}
	let sendingConvert = $state(false);
	async function onClickConvert() {
		if (sendingConvert) return;
		sendingConvert = true;
		const { data, error } = await ImagesService.imageConvert({ path: { id: file.id } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else if (data) {
			// A brand-new comic was imported; drop the cached comic list so it shows
			// up when navigating to comics instead of only after a reload.
			refreshMediaFiles(MediaType.Comic);
			addNotification(new SuccessNotification({ subtitle: `Converted to comic: ${data.name}` }));
		}
		sendingConvert = false;
	}

	let loadingDetail = $state(false);
	// Comics and image albums share the same `{ pageDetails: [{ name }] }` shape;
	// only the service that produces it differs.
	let detail = $state<{ pageDetails: { name: string }[] }>();
	async function onClickDetail() {
		loadingDetail = true;
		const { data, error } =
			mediaType === MediaType.Image
				? await ImagesService.imageDetail({ path: { id: file.id } })
				: await ComicsService.comicDetail({ path: { id: file.id } });
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else {
			detail = data;
		}
		loadingDetail = false;
	}

	// Index of the album page currently being deleted (-1 when idle), so only its
	// row shows a spinner and double-clicks are ignored.
	let deletingPageIdx = $state(-1);
	async function onClickDeletePage(idx: number) {
		if (deletingPageIdx !== -1) return;
		deletingPageIdx = idx;
		// The API is 1-based and deletes by position in the sorted file list, which
		// matches this list's order, so the local row index maps straight to a page.
		const { data, error } = await ImagesService.imageDeletePage({
			path: { id: file.id, page: idx + 1 }
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else if (data) {
			// Drop the row locally so the remaining rows stay aligned with the
			// folder for any follow-up deletes, and reflect the new page count/cover
			// on the shared file instance held by cached list views.
			detail = { pageDetails: (detail?.pageDetails ?? []).filter((_, i) => i !== idx) };
			file.update(data);
			refreshMediaFiles(MediaType.Image);
		}
		deletingPageIdx = -1;
	}
</script>

<Modal
	bind:open
	modalLabel={`ID: ${file.id}`}
	modalHeading={`${file.name}`}
	size="sm"
	on:close={() => onCloseModal()}
	primaryButtonText="Go!"
	primaryButtonDisabled={sendingDelete ||
		sendingRefresh ||
		sendingFavorite ||
		sendingRename ||
		sendingConvert ||
		file.archived}
	on:click:button--primary={() => onClickPrimaryButton()}
>
	<div style="display: flex; align-items: center;">
		<TextInput labelText="Name" bind:value={newname} inline readonly={!editingName} />
		{#if editingName}
			<Button
				icon={Save}
				iconDescription="Save"
				on:click={() => {
					onClickSaveName();
				}}
				disabled={sendingRename}
			/>
		{:else}
			<Button
				icon={Edit}
				iconDescription="Edit"
				on:click={() => {
					editingName = true;
				}}
			/>
		{/if}
	</div>
	<div class="horizontal">
		<TextInput labelText="Size" value={file.size > 0 ? `${file.size}MB` : 'Unknown'} readonly />
		{#if comicfile}
			<TextInput labelText="Page" value={comicfile.page} readonly />
		{/if}
		{#if videofile}
			<TextInput labelText="Duration" value={videofile.durationInSecond} readonly />
		{/if}
	</div>
	<div class="horizontal">
		<TextInput labelText="Update Time" value={file.updateTime} readonly />
		<TextInput labelText="Last Viewed" value={file.lastViewedLabel} readonly />
	</div>
	<div>
		<p>Tags</p>
		{#each separateFilename(separateToTagsFrom ?? '') as tag}
			<span class="tag-wrap">
				<Tag type="teal" title={tag} on:click={() => onClickTag(tag)} interactive={true}>{tag}</Tag>
				<button
					type="button"
					class="tag-global"
					title={`Search "${tag}" everywhere`}
					aria-label={`Search "${tag}" everywhere`}
					onclick={() => goto(`/search?q=${encodeURIComponent(tag)}`)}
				>
					<SearchIcon size={16} />
				</button>
			</span>
		{/each}
	</div>

	<p>Actions:</p>
	<div class="actions">
		<Button
			kind="danger"
			on:click={() => {
				openDeleteModal = true;
			}}
			icon={TrashCan}
			iconDescription="Delete"
			disabled={sendingDelete}
		/>
		<span class="fav-wrap" class:favorited={file.favorited}>
			<Button
				icon={file.favorited ? FavoriteFilled : Favorite}
				iconDescription="Favorite"
				on:click={() => onClickFavorite()}
				disabled={sendingFavorite || file.archived}
			/>
		</span>
		<Button
			icon={UpdateNow}
			iconDescription="Refresh"
			on:click={() => onClickRefresh()}
			disabled={sendingRefresh || file.archived || mediaType === MediaType.Video}
		/>
		<CopyButton text={file.name} />
		<Button
			icon={NewTab}
			iconDescription="NewTab"
			on:click={() => {
				window.open(`/${mediaType}/${file.id}`);
			}}
			disabled={file.archived}
		/>
		<Button
			icon={ApplicationWeb}
			iconDescription="External Application"
			href={`honeyview:${file.path}`}
			disabled={file.archived}
		/>
		{#if mediaType === MediaType.Image}
			<Button
				icon={Book}
				iconDescription="Convert to comic"
				on:click={() => onClickConvert()}
				disabled={sendingConvert || file.archived}
			/>
		{/if}
		{#if sendingRefresh || sendingDelete || sendingFavorite || sendingRename || sendingConvert}
			<InlineLoading />
		{/if}
	</div>
	<TextArea labelText="Path" value={file.path} readonly rows={3} />
	{#if !file.archived}
		<p>Details</p>
		<DataTable
			headers={mediaType === MediaType.Image
				? [
						{ key: 'name', value: 'Name' },
						{ key: 'actions', empty: true }
					]
				: [{ key: 'name', value: 'Name' }]}
			rows={detail?.pageDetails.map((page, idx) => ({ id: idx, name: page.name })) ?? []}
		>
			<svelte:fragment slot="cell" let:row let:cell>
				{#if cell.key === 'actions'}
					{#if deletingPageIdx === row.id}
						<InlineLoading />
					{:else}
						<Button
							kind="danger-ghost"
							size="small"
							icon={TrashCan}
							iconDescription="Delete image"
							tooltipPosition="left"
							disabled={deletingPageIdx !== -1}
							on:click={() => onClickDeletePage(row.id)}
						/>
					{/if}
				{:else}
					{cell.value}
				{/if}
			</svelte:fragment>
		</DataTable>
		{#if loadingDetail}
			<InlineLoading description="Loading..." />
		{/if}
		{#if detail === undefined && !loadingDetail}
			<div class="center">
				<Button
					kind="secondary"
					on:click={() => {
						onClickDetail();
					}}>Load</Button
				>
			</div>
		{/if}
	{/if}
</Modal>

<ComposedModal bind:open={openDeleteModal} on:click:button--primary={() => onClickDelete()}>
	<ModalHeader
		label="Changes"
		title="Confirm delete {mediaType === MediaType.Image
			? 'image folder'
			: mediaType === MediaType.Video
				? 'video'
				: 'comic'}"
	/>
	<ModalBody hasForm>
		{#if mediaType !== MediaType.Image}
			<Checkbox labelText="permenant: including database record" bind:checked={permanent} />
		{/if}
		{#if sendingDelete}
			<InlineLoading description="Deleting..." />
		{/if}
	</ModalBody>
	<ModalFooter primaryButtonText="Proceed" />
</ComposedModal>

<style>
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-start;
		align-items: center;
		gap: 0.5rem;
	}

	.fav-wrap :global(svg) {
		transition: transform 0.15s ease;
	}

	.fav-wrap.favorited :global(svg) {
		color: #da1e28;
		animation: fav-pop 0.3s ease;
	}

	@keyframes fav-pop {
		0% {
			transform: scale(1);
		}
		40% {
			transform: scale(1.45);
		}
		70% {
			transform: scale(0.85);
		}
		100% {
			transform: scale(1);
		}
	}

	.center {
		display: flex;
		justify-content: center;
		align-items: center;
	}

	.horizontal {
		display: flex;
		flex-direction: row;
		gap: 0.5rem;
	}

	.tag-wrap {
		display: inline-flex;
		align-items: center;
	}

	.tag-global {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		margin: 0 0.5rem 0 -0.25rem;
		padding: 0.125rem;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--cds-text-03, #8d8d8d);
	}

	.tag-global:hover {
		color: var(--cds-text-01, #f4f4f4);
	}

	p {
		color: #c6c6c6;
		font-size: 0.75rem;
		font-weight: 400;
		letter-spacing: 0.32px;
		line-height: 1rem;
		margin-bottom: 0.5rem;
	}
</style>
