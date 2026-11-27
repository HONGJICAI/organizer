<script lang="ts">
	// Admin -> Media sources: the scan folders of each media type. Built-in
	// ones come from the environment (compose.yaml); more can be added here,
	// picked from the folders the server (container) can see.
	import { onMount } from 'svelte';
	import { SystemService } from '$lib/client';
	import type { FolderListing, MediaSourceInfo } from '$lib/client';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import {
		Button,
		Dropdown,
		InlineNotification,
		Modal,
		Tag,
		TextInput,
		Tile
	} from 'carbon-components-svelte';
	import { Add, DataBase, Folder, FolderParent, TrashCan } from 'carbon-icons-svelte';

	// Called after a change queued a scan, so the page can show it.
	let { onscan }: { onscan?: () => void } = $props();

	type Media = MediaSourceInfo['media'];
	const medias: { id: Media; text: string }[] = [
		{ id: 'comic', text: 'Comics' },
		{ id: 'video', text: 'Videos' },
		{ id: 'image', text: 'Images' }
	];
	const statusText: Record<MediaSourceInfo['status'], string> = {
		ok: '',
		not_found: 'Not found',
		not_mounted: 'Not mounted'
	};
	const statusHint: Record<MediaSourceInfo['status'], string> = {
		ok: '',
		not_found:
			'The folder is missing, e.g. an unmounted drive. Scans keep its items as they are until it is back.',
		not_mounted:
			"Not on a mounted drive: it's inside the container, where nothing from the host is."
	};
	const scanText = {
		started: 'a scan started',
		queued: 'a scan is queued',
		already_queued: 'a waiting scan covers it'
	};

	let sources = $state<MediaSourceInfo[] | null>(null);
	let media = $state<Media>('comic');
	let path = $state('');
	let adding = $state(false);
	let addError = $state('');
	let removing = $state<MediaSourceInfo | null>(null);
	let removeBusy = $state(false);
	let picker = $state<FolderListing | null>(null);
	let pickerOpen = $state(false);
	let pickerError = $state('');

	const errorMsg = (error: unknown, fallback: string) =>
		error && typeof error === 'object' && 'msg' in error && typeof error.msg === 'string'
			? error.msg
			: fallback;

	async function load() {
		const { data, error } = await SystemService.listMediaSources();
		if (!error && data) sources = data;
	}

	async function add() {
		adding = true;
		addError = '';
		const { data, error } = await SystemService.addMediaSource({ body: { media, path } });
		adding = false;
		if (error || !data) {
			addError = errorMsg(error, "Couldn't add the folder");
			return;
		}
		path = '';
		addNotification(
			new SuccessNotification({ subtitle: `Added ${data.source.path}; ${scanText[data.scan]}` })
		);
		await load();
		onscan?.();
	}

	async function remove() {
		const source = removing;
		if (source?.id == null) return;
		removeBusy = true;
		const { data, error } = await SystemService.removeMediaSource({ path: { id: source.id } });
		removeBusy = false;
		removing = null;
		if (error || !data) {
			addNotification(
				new ErrorNotification({ subtitle: errorMsg(error, `Couldn't remove ${source.path}`) })
			);
			return;
		}
		addNotification(
			new SuccessNotification({ subtitle: `Removed ${source.path}; ${scanText[data.scan]}` })
		);
		await load();
		onscan?.();
	}

	async function browse(to?: string | null) {
		pickerError = '';
		const { data, error } = await SystemService.listFolders({
			query: to ? { path: to } : undefined
		});
		if (error || !data) {
			pickerError = errorMsg(error, "Couldn't list the folder");
			return;
		}
		picker = data;
	}

	function openPicker() {
		pickerOpen = true;
		// Start where the typed path points, else at the media folder.
		browse(path.trim().startsWith('/') ? path.trim() : null);
	}

	function choose() {
		if (picker) path = picker.path;
		pickerOpen = false;
	}

	onMount(load);
</script>

<Tile class="card">
	<div class="card-head">
		<h3>Media sources</h3>
	</div>
	<p class="muted note">
		Folders scanned for each media type. Built-in ones come from compose.yaml; added folders must be
		inside a drive or share mounted there. A folder that is missing or empty (an unmounted drive, a
		share that's down) keeps its items as they are until it's back.
	</p>
	{#each medias as m (m.id)}
		{@const rows = sources?.filter((s) => s.media === m.id) ?? []}
		<h4>{m.text}</h4>
		<ul class="sources">
			{#each rows as source (source.id ?? source.path)}
				<li>
					<span class="path" title={source.path}>{source.path}</span>
					{#if source.status !== 'ok'}
						<Tag
							type={source.status === 'not_found' ? 'red' : 'warm-gray'}
							size="sm"
							title={statusHint[source.status]}>{statusText[source.status]}</Tag
						>
					{/if}
					{#if source.builtin}
						<Tag type="gray" size="sm">Built-in</Tag>
					{:else}
						<Button
							kind="ghost"
							size="small"
							icon={TrashCan}
							iconDescription="Remove"
							on:click={() => (removing = source)}
						/>
					{/if}
				</li>
			{:else}
				<li class="muted">{sources ? 'None' : 'Loading…'}</li>
			{/each}
		</ul>
	{/each}

	<h4>Add a folder</h4>
	<div class="add">
		<Dropdown size="sm" titleText="Media" hideLabel items={medias} bind:selectedId={media} />
		<TextInput
			size="sm"
			labelText="Folder"
			hideLabel
			placeholder="/data/…"
			bind:value={path}
			on:keydown={(e) => {
				if (e.key === 'Enter' && path.trim()) add();
			}}
		/>
		<div class="add-actions">
			<Button kind="secondary" size="small" icon={Folder} on:click={openPicker}>Browse</Button>
			<Button size="small" icon={Add} disabled={adding || !path.trim()} on:click={add}>Add</Button>
		</div>
	</div>
	{#if addError}
		<InlineNotification
			kind="error"
			lowContrast
			hideCloseButton
			title="Not added:"
			subtitle={addError}
		/>
	{/if}
</Tile>

<Modal
	open={removing !== null}
	danger
	modalHeading="Remove media source"
	primaryButtonText={removeBusy ? 'Removing…' : 'Remove'}
	primaryButtonDisabled={removeBusy}
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (removing = null)}
	on:close={() => (removing = null)}
	on:submit={remove}
>
	<p>
		Stop scanning <code>{removing?.path}</code>? Nothing on disk changes. The scan that follows
		lists its comics and videos under Cleanup → Missing files and drops its image albums; adding the
		folder again brings them back.
	</p>
</Modal>

<Modal
	bind:open={pickerOpen}
	modalHeading="Choose a folder"
	primaryButtonText="Use this folder"
	primaryButtonDisabled={!picker}
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (pickerOpen = false)}
	on:submit={choose}
>
	{#if picker}
		<p class="picker-path"><code>{picker.path}</code></p>
		<ul class="folders">
			{#if picker.parent}
				<li>
					<button type="button" onclick={() => browse(picker?.parent)}>
						<FolderParent size={16} /><span>..</span>
					</button>
				</li>
			{/if}
			{#each picker.dirs as dir (dir.path)}
				<li>
					<button type="button" onclick={() => browse(dir.path)}>
						{#if dir.mount}<DataBase size={16} />{:else}<Folder size={16} />{/if}
						<span>{dir.name}</span>
						{#if dir.mount}<Tag type="teal" size="sm">Mounted</Tag>{/if}
					</button>
				</li>
			{:else}
				<li class="muted">No subfolders</li>
			{/each}
		</ul>
	{/if}
	{#if pickerError}
		<InlineNotification kind="error" lowContrast hideCloseButton subtitle={pickerError} />
	{/if}
</Modal>

<style>
	.card-head h3 {
		margin: 0;
	}

	.muted {
		color: var(--cds-text-02, #c6c6c6);
	}

	.note {
		font-size: 0.875rem;
	}

	h4 {
		margin: 0;
	}

	.sources,
	.folders {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.sources li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 2rem;
		font-size: 0.875rem;
	}

	.path {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-family: var(--cds-code-01-font-family, monospace);
	}

	.add {
		display: grid;
		grid-template-columns: 7rem minmax(0, 1fr);
		gap: 0.5rem;
		align-items: center;
	}

	.add-actions {
		grid-column: 1 / -1;
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}

	.picker-path {
		margin-bottom: 0.5rem;
		word-break: break-all;
	}

	.folders {
		max-height: 50vh;
		overflow-y: auto;
	}

	.folders button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.5rem;
		border: none;
		background: none;
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}

	.folders button:hover,
	.folders button:focus-visible {
		background: var(--cds-hover-ui, #353535);
	}

	.folders li.muted {
		padding: 0.5rem;
	}
</style>
