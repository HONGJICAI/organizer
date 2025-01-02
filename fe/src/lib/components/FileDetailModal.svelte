<script lang="ts">
	import {
		Button,
		Checkbox,
		ComposedModal,
		CopyButton,
		InlineLoading,
		Modal,
		ModalBody,
		ModalFooter,
		ModalHeader,
		Tag,
		TextArea,
		TextInput
	} from 'carbon-components-svelte';
	import { Comic, MediaType, type MediaFile, Video } from '$lib/model';
	import { separateFilename } from '$lib/utility';
	import { config } from '$lib/config';
	import {
		ApplicationWeb,
		Favorite,
		FavoriteFilled,
		NewTab,
		TrashCan,
		UpdateNow
	} from 'carbon-icons-svelte';

	export let open = false;
	export let onCloseModal = () => {};
	export let file: MediaFile;
	export let onClickTag = (tag: string) => {};
	export let onClickPrimaryButton = () => {};
	export let onFileDeleted = (permenant: boolean) => {};
	$: mediaType = file.type;
	$: comicfile = file.type === MediaType.Comic ? (file as Comic) : null;
	$: videofile = file.type === MediaType.Video ? (file as Video) : null;
	$: separateToTagsFrom = file.type === MediaType.Comic ? file.name : file.path;
	let permenant = false;
	let openDeleteModal = false;
	let sendingDelete = false;
	let deleteError = '';
	let onClickDelete = async () => {
		if (sendingDelete) {
			return;
		}

		let rsp: Response;
		sendingDelete = true;
		try {
			switch (mediaType) {
				case MediaType.Comic:
					rsp = await fetch(`${config.apiServer}/api/comics/${file.id}?permenant=${permenant}`, {
						method: 'DELETE'
					});
					break;
				case MediaType.Video:
					rsp = await fetch(`${config.apiServer}/api/videos/${file.id}?permenant=${permenant}`, {
						method: 'DELETE'
					});
					break;
				default:
					alert(`Unknown media type: ${mediaType}`);
					throw new Error(`Unknown media type: ${mediaType}`);
			}
			if (rsp.ok) {
				onFileDeleted(permenant);
				onCloseModal();
			} else {
				console.log(rsp);
				const json = await rsp.json();
				deleteError = `Error: ${rsp.status} ${json.error}`;
			}
		} catch (e) {
			deleteError = `Error: ${e}`;
			throw e;
		} finally {
			sendingDelete = false;
		}
	};
	let sendingLike = false;
	const onClickLike = async () => {
		if (sendingLike) {
			return;
		}
		sendingLike = true;
		const rsp = await fetch(
			`${config.apiServer}/api/comics/${file.id}/${file.like ? 'unlike' : 'like'}`,
			{ method: 'POST' }
		);
		sendingLike = false;
		if (rsp.ok) {
			file.like = !file.like;
		} else {
			alert(rsp.status);
		}
	};

	let sendingRefresh = false;
	async function onClickRefresh(): Promise<void> {
		if (sendingRefresh) {
			return;
		}
		sendingRefresh = true;
		const rsp = await fetch(`${config.apiServer}/api/comics/${file.id}/refresh`, {
			method: 'POST'
		});
		sendingRefresh = false;
		if (rsp.ok) {
			var json = await rsp.json();
			var f = mediaType === MediaType.Comic ? new Comic(json) : new Video(json);
			file.like = f.like;
			file.lastViewedTime = f.lastViewedTime;
			file.page = f.page;
		} else {
			alert(rsp.status);
		}
	}
</script>

<Modal
	bind:open
	modalHeading={file.name}
	size="sm"
	on:close={() => onCloseModal()}
	primaryButtonText="Go!"
	on:click:button--primary={() => onClickPrimaryButton()}
>
	<TextInput labelText="ID" value={file.id} readonly inline />
	<TextInput labelText="Size" value={`${file.size}MB`} readonly inline />
	{#if comicfile}
		<TextInput labelText="Page" value={comicfile.page} readonly inline />
	{/if}
	{#if videofile}
		<TextInput labelText="Duration" value={videofile.durationInSecond} readonly inline />
	{/if}
	<TextInput labelText="Update Time" value={file.updateTime} readonly inline />
	<TextInput labelText="Last Viewed" value={file.lastViewedLabel} readonly inline />
	<div>
		<p>Tags:</p>
		{#each separateFilename(separateToTagsFrom ?? '') as tag}
			<Tag type="teal" title={tag} on:click={() => onClickTag(tag)}>{tag}</Tag>
		{/each}
	</div>

	<p>Actions:</p>
	<container>
		{#if sendingDelete}
			<InlineLoading />
		{:else}
			<Button
				kind="danger"
				on:click={() => {
					openDeleteModal = true;
				}}
				icon={TrashCan}
				iconDescription="Delete"
			/>
		{/if}
		{#if sendingLike}
			<InlineLoading />
		{:else}
			<Button
				icon={file.like ? FavoriteFilled : Favorite}
				iconDescription="Like"
				on:click={() => onClickLike()}
			/>
		{/if}
		<Button icon={UpdateNow} iconDescription="Refresh" on:click={() => onClickRefresh()} />
		<CopyButton text={file.name} />
		<Button
			icon={NewTab}
			iconDescription="NewTab"
			on:click={() => {
				window.open(`/${mediaType}/${file.id}`);
			}}
		/>
		<Button
			icon={ApplicationWeb}
			iconDescription="External Application"
			href={`honeyview:${file.path}`}
		/>
	</container>
	<TextArea labelText="Path" value={file.path} readonly />
</Modal>

<ComposedModal bind:open={openDeleteModal} on:click:button--primary={() => onClickDelete()}>
	<ModalHeader label="Changes" title="Confirm delete" />
	<ModalBody hasForm>
		<Checkbox labelText="permenant" bind:checked={permenant} />
		{deleteError}
	</ModalBody>
	<ModalFooter primaryButtonText="Proceed" />
</ComposedModal>

<style>
	container {
		display: flex;
		justify-content: flex-start;
		align-items: center;
		gap: 0.5rem;
	}
</style>
