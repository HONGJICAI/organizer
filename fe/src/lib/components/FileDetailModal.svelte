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
		Image,
		MediaType,
		type MediaFile,
		Video,
		SuccessNotification,
		ErrorNotification
	} from '$lib/model.svelte';
	import { separateFilename } from '$lib/utility';
	import {
		ApplicationWeb,
		Edit,
		Favorite,
		FavoriteFilled,
		NewTab,
		Save,
		TrashCan,
		UpdateNow
	} from 'carbon-icons-svelte';
	import {
		ComicsService,
		ImagesService,
		VideosService,
		type ComicDetailResponse
	} from '$lib/client';
	import { addNotification } from '$lib/state.svelte';

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
					file = new Comic(data);
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
					file = new Image(data);
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
	let loadingDetail = $state(false);
	let comicDetail = $state<ComicDetailResponse>();
	async function onClickDetail() {
		loadingDetail = true;
		const { data, error } = await ComicsService.comicDetail({
			path: {
				id: file.id
			}
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: error?.msg }));
		} else {
			comicDetail = data;
		}
		loadingDetail = false;
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
			<Tag type="teal" title={tag} on:click={() => onClickTag(tag)} interactive={true}>{tag}</Tag>
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
		{#if sendingRefresh || sendingDelete || sendingFavorite || sendingRename}
			<InlineLoading />
		{/if}
	</div>
	<TextArea labelText="Path" value={file.path} readonly rows={3} />
	{#if !file.archived}
		<p>Details</p>
		<DataTable
			headers={[{ key: 'name', value: 'Name' }]}
			rows={comicDetail?.pageDetails.map((page, idx) => ({ id: idx, name: page.name })) ?? []}
		/>
		{#if loadingDetail}
			<InlineLoading description="Loading..." />
		{/if}
		{#if comicDetail === undefined && !loadingDetail}
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

	p {
		color: #c6c6c6;
		font-size: 0.75rem;
		font-weight: 400;
		letter-spacing: 0.32px;
		line-height: 1rem;
		margin-bottom: 0.5rem;
	}
</style>
