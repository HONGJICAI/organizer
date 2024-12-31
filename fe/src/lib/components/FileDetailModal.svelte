<script lang="ts">
	import { Button, CopyButton, InlineLoading, Modal, Tag, TextArea, TextInput } from 'carbon-components-svelte';
	import { Comic, MediaType, type MediaFile, Video } from '$lib/model';
	import { separateFilename } from '$lib/utility';
	import { config } from '$lib/config';
	import { ApplicationWeb, Favorite, FavoriteFilled, NewTab, TrashCan, UpdateNow } from 'carbon-icons-svelte';

	export let open = false;
	export let onCloseModal = () => {};
	export let file: MediaFile;
	export let onClickTag = (tag: string) => {};
	export let onClickPrimaryButton = () => {};
	export let onFileDeleted = () => {};
	$: mediaType = file.type;
	$: comicfile = file.type === MediaType.Comic ? (file as Comic) : null;
	$: videofile = file.type === MediaType.Video ? (file as Video) : null;
	$: separateToTagsFrom = file.type === MediaType.Comic ? file.name : file.path;
	let sendingDelete = false;
	let onClickDelete = async () => {
		if (sendingDelete) {
			return;
		}
		const yes = confirm(`Are you sure to delete ${file.name}?`);
		if (!yes) {
			return;
		}

		let rsp: Response;
		sendingDelete = true;
		switch (mediaType) {
			case MediaType.Comic:
				rsp = await fetch(`${config.apiServer}/api/comics/${file.id}`, {
					method: 'DELETE'
				});
				break;
			case MediaType.Video:
				rsp = await fetch(`${config.apiServer}/api/videos/${file.id}`, {
					method: 'DELETE'
				});
				break;
			default:
				alert(`Unknown media type: ${mediaType}`);
				throw new Error(`Unknown media type: ${mediaType}`);
		}
		sendingDelete = false;

		if (rsp.ok) {
			onFileDeleted();
			onCloseModal();
		} else {
			console.log(rsp);
			alert(rsp.status);
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
		const rsp = await fetch(
			`${config.apiServer}/api/comics/${file.id}/refresh`,
			{ method: 'POST' }
		);
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
	<TextInput labelText="Last Viewed" value={file.lastViewedTime} readonly inline />
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
				on:click={() => onClickDelete()}
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
			<Button
				icon={UpdateNow}
				iconDescription="Refresh"
				on:click={() => onClickRefresh()}
			/>
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

<style>
	container {
		display: flex;
		justify-content: flex-start;
		align-items: center;
		gap: 0.5rem;
	}
</style>
