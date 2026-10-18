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
		TagEdit,
		TrashCan,
		UpdateNow
	} from 'carbon-icons-svelte';
	import { adapters, type PageDetail } from '$lib/mediaAdapters';
	import { formatBytes } from '$lib/stats';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import { goto } from '$app/navigation';
	import { kindColor, kindLabel, tagKinds, type TagKind } from '$lib/tagIndex';
	import { loadTags, setTagKind, tagState } from '$lib/tags.svelte';

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
	let adapter = $derived(adapters[file.type]);
	let separateToTagsFrom = $derived(adapter.tagSource(file));
	// Tag classification: the tag whose kind picker is open, if any.
	loadTags();
	let classifying = $state<string | null>(null);
	let savingKind = $state(false);
	async function classify(tag: string, kind: TagKind | null) {
		savingKind = true;
		// An alias is classified through its primary tag.
		const error = await setTagKind([tagState.index.canonical(tag)], kind);
		savingKind = false;
		if (error) addNotification(new ErrorNotification({ subtitle: error }));
		else classifying = null;
	}
	let permanent = $state(false);
	let openDeleteModal = $state(false);
	let sendingDelete = $state(false);
	async function onClickDelete() {
		sendingDelete = true;
		openDeleteModal = false;
		const { error } = await adapter.remove(file.id, permanent);
		if (error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: error }));
		} else {
			onFileDeleted(permanent || !adapter.archivable);
			// The per-type list is cached for the session (see mediaStore); drop it
			// so navigating away and back re-fetches instead of resurrecting the
			// just-deleted/archived file from stale cache.
			refreshMediaFiles(mediaType);
			onCloseModal();
		}
		sendingDelete = false;
	}
	let sendingFavorite = $state(false);
	const onClickFavorite = async () => {
		if (sendingFavorite || !adapter.favor) {
			return;
		}
		sendingFavorite = true;
		const result = await adapter.favor(file.id, !file.favorited);
		if (result.error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: result.error }));
		} else {
			file.favorited = result.data;
		}
		sendingFavorite = false;
	};

	let sendingRefresh = $state(false);
	async function onClickRefresh() {
		if (!adapter.refresh) return;
		sendingRefresh = true;
		const result = await adapter.refresh(file.id);
		if (result.error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: result.error }));
		} else {
			// update in place so the same object held by cached list views
			// reflects the refresh, instead of replacing it with a new instance
			file.update(result.data);
			addNotification(new SuccessNotification({ subtitle: `Refreshed ${file.name}` }));
		}
		sendingRefresh = false;
	}
	let editingName = $state(false);
	let newname = $state(file.name);
	let sendingRename = $state(false);
	async function onClickSaveName() {
		if (!adapter.rename) return;
		sendingRename = true;
		const { error } = await adapter.rename(file.id, newname);
		if (error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: error }));
		} else {
			editingName = false;
			file.name = newname;
			addNotification(new SuccessNotification({ subtitle: `Renamed to ${newname}` }));
		}
		sendingRename = false;
	}
	let sendingConvert = $state(false);
	async function onClickConvert() {
		if (sendingConvert || !adapter.convertToComic) return;
		sendingConvert = true;
		const result = await adapter.convertToComic(file.id);
		if (result.error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: result.error }));
		} else {
			// A brand-new comic was imported; drop the cached comic list so it shows
			// up when navigating to comics instead of only after a reload.
			refreshMediaFiles(MediaType.Comic);
			addNotification(new SuccessNotification({ subtitle: `Converted to comic: ${result.data}` }));
		}
		sendingConvert = false;
	}

	let loadingDetail = $state(false);
	let detail = $state<{ pageDetails: PageDetail[] }>();
	async function onClickDetail() {
		if (!adapter.detail) return;
		loadingDetail = true;
		const result = await adapter.detail(file.id);
		if (result.error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: result.error }));
		} else {
			detail = result.data;
		}
		loadingDetail = false;
	}

	// Index of the album page currently being deleted (-1 when idle), so only its
	// row shows a spinner and double-clicks are ignored.
	let deletingPageIdx = $state(-1);
	async function onClickDeletePage(idx: number) {
		if (deletingPageIdx !== -1 || !adapter.deletePage) return;
		deletingPageIdx = idx;
		// The API is 1-based and deletes by position in the sorted file list, which
		// matches this list's order, so the local row index maps straight to a page.
		const result = await adapter.deletePage(file.id, idx + 1);
		if (result.error !== undefined) {
			addNotification(new ErrorNotification({ subtitle: result.error }));
		} else {
			// Drop the row locally so the remaining rows stay aligned with the
			// folder for any follow-up deletes, and reflect the new page count/cover
			// on the shared file instance held by cached list views.
			detail = { pageDetails: (detail?.pageDetails ?? []).filter((_, i) => i !== idx) };
			file.update(result.data);
			refreshMediaFiles(mediaType);
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
		{#if adapter.rename && editingName}
			<Button
				icon={Save}
				iconDescription="Save"
				on:click={() => {
					onClickSaveName();
				}}
				disabled={sendingRename}
			/>
		{:else if adapter.rename}
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
			{@const kind = tagState.index.kind(tag)}
			{@const primary = tagState.index.canonical(tag)}
			<span class="tag-wrap">
				<Tag
					type={kindColor[kind ?? 'none']}
					title={`${tag}${kind ? ` · ${kindLabel[kind]}` : ''}${primary !== tag ? ` · alias of ${primary}` : ''}`}
					on:click={() => onClickTag(primary)}
					interactive={true}>{tag}</Tag
				>
				<button
					type="button"
					class="tag-global"
					class:active={classifying === tag}
					title={`Classify "${tag}"`}
					aria-label={`Classify "${tag}"`}
					aria-expanded={classifying === tag}
					onclick={() => (classifying = classifying === tag ? null : tag)}
				>
					<TagEdit size={16} />
				</button>
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
		{#if classifying}
			{@const current = tagState.index.kind(classifying)}
			{@const primary = tagState.index.canonical(classifying)}
			<div class="classify">
				<span class="classify-label"
					>“{primary}”{primary !== classifying ? ` (via alias “${classifying}”)` : ''} is</span
				>
				{#each tagKinds as kind (kind)}
					<Button
						size="small"
						kind={current === kind ? 'primary' : 'tertiary'}
						disabled={savingKind}
						on:click={() => classify(classifying ?? '', kind)}>{kindLabel[kind]}</Button
					>
				{/each}
				{#if current}
					<Button
						size="small"
						kind="ghost"
						disabled={savingKind}
						on:click={() => classify(classifying ?? '', null)}>Unclassify</Button
					>
				{/if}
			</div>
		{/if}
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
		<!-- Only comics can be favorited: image albums are kept lightweight
		     (convert one to a comic to keep it) and videos have no favor API. -->
		{#if adapter.favor}
			<span class="fav-wrap" class:favorited={file.favorited}>
				<Button
					icon={file.favorited ? FavoriteFilled : Favorite}
					iconDescription="Favorite"
					on:click={() => onClickFavorite()}
					disabled={sendingFavorite || file.archived}
				/>
			</span>
		{/if}
		{#if adapter.refresh}
			<Button
				icon={UpdateNow}
				iconDescription="Refresh"
				on:click={() => onClickRefresh()}
				disabled={sendingRefresh || file.archived}
			/>
		{/if}
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
		{#if adapter.convertToComic}
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
	{#if !file.archived && adapter.detail}
		<p>Details</p>
		<DataTable
			sortable
			headers={[
				{ key: 'page', value: '#' },
				{ key: 'name', value: 'Name' },
				{ key: 'size', value: 'Size' },
				...(adapter.deletePage ? [{ key: 'actions', empty: true, sort: false as const }] : [])
			]}
			rows={detail?.pageDetails.map((page, idx) => ({
				id: idx,
				page: idx + 1,
				name: page.name,
				size: page.size
			})) ?? []}
		>
			<svelte:fragment slot="cell" let:row let:cell>
				{#if cell.key === 'size'}
					{formatBytes(cell.value)}
				{:else if cell.key === 'actions'}
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
	<ModalHeader label="Changes" title="Confirm delete {adapter.label}" />
	<ModalBody hasForm>
		{#if adapter.archivable}
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

	.tag-global:hover,
	.tag-global.active {
		color: var(--cds-text-01, #f4f4f4);
	}

	.classify {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin: 0.5rem 0;
	}

	.classify-label {
		font-size: 0.875rem;
		overflow-wrap: anywhere;
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
