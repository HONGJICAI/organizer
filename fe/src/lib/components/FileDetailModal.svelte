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
	import { Comic, MediaType, type MediaFile, Video } from '$lib/model.svelte';
	import { separateFilename } from '$lib/utility';
	import { config } from '$lib/config';
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

	interface Props {
		open?: boolean;
		onCloseModal?: any;
		file: MediaFile;
		onClickTag?: (tag: string) => void;
		onClickPrimaryButton?: any;
		onFileDeleted?: any;
	}

	let {
		open = $bindable(false),
		onCloseModal = () => {},
		file = $bindable(),
		onClickTag = (tag: string) => {},
		onClickPrimaryButton = () => {},
		onFileDeleted = (permenant: boolean) => {}
	}: Props = $props();
	let mediaType = $derived(file.type);
	let comicfile = $derived(file.type === MediaType.Comic ? (file as Comic) : null);
	let videofile = $derived(file.type === MediaType.Video ? (file as Video) : null);
	let separateToTagsFrom = $derived(file.type === MediaType.Comic ? file.name : file.path);
	let permenant = $state(false);
	let openDeleteModal = $state(false);
	let sendingDelete = $state(false);
	let deleteError = $state('');
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
	let sendingFavorite = $state(false);
	const onClickFavorite = async () => {
		if (sendingFavorite) {
			return;
		}
		sendingFavorite = true;
		const rsp = await fetch(
			`${config.apiServer}/api/comics/${file.id}/favor`,
			{ method: file.favorited ? 'DELETE' : 'POST' }
		);
		sendingFavorite = false;
		if (rsp.ok) {
			file.favorited = !file.favorited;
		} else {
			alert(rsp.status);
		}
	};

	let sendingRefresh = $state(false);
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
			file.favorited = f.favorited;
			file.lastViewedTime = f.lastViewedTime;
			if (mediaType === MediaType.Comic) {
				(file as Comic).page = (f as Comic).page;
			}
		} else {
			alert(rsp.status);
		}
	}
	let editingName = $state(false);
	let newname = $state(file.name);
	async function onClickSaveName() {
		const rsp = await fetch(`${config.apiServer}/api/comics/${file.id}/rename`, {
			method: 'POST',
			body: JSON.stringify({ name: newname }),
			headers: {
				'Content-Type': 'application/json'
			}
		});
		if (rsp.ok) {
			editingName = false;
			const json = await rsp.json();
			const comic = new Comic(json);
			file.name = comic.name;
		} else {
			alert(rsp.status);
			throw new Error(`${rsp.status}`);
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
	<div style="display: flex; align-items: center;">
		<TextInput labelText="Name" bind:value={newname} inline readonly={!editingName} />
		{#if editingName}
			<Button
				icon={Save}
				iconDescription="Save"
				on:click={() => {					
					onClickSaveName();
				}}
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
		{#if sendingFavorite}
			<InlineLoading />
		{:else}
			<Button
				icon={file.favorited ? FavoriteFilled : Favorite}
				iconDescription="Favorite"
				on:click={() => onClickFavorite()}
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
	<ModalHeader label="Changes" title="Confirm delete the comic file" />
	<ModalBody hasForm>
		<Checkbox labelText="permenant: including database record" bind:checked={permenant} />
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
