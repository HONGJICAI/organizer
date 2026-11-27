<script lang="ts">
	// Admin -> Media sources: the scan folders of each media type. Built-in
	// ones come from the environment (compose.yaml); more can be added here:
	// folders the server (container) can see, or SMB shares it mounts itself.
	import { onMount } from 'svelte';
	import { SystemService } from '$lib/client';
	import type { FolderListing, MediaSourceInfo, SmbSupport } from '$lib/client';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import {
		Button,
		ContentSwitcher,
		Dropdown,
		InlineNotification,
		Modal,
		PasswordInput,
		Switch,
		Tag,
		TextInput,
		Tile
	} from 'carbon-components-svelte';
	import {
		Add,
		DataBase,
		Edit,
		Folder,
		FolderParent,
		Network_3,
		Renew,
		TrashCan
	} from 'carbon-icons-svelte';

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
		not_mounted: 'Not mounted',
		not_connected: 'Not connected'
	};
	const statusHint: Record<MediaSourceInfo['status'], string> = {
		ok: '',
		not_found:
			'The folder is missing, e.g. an unmounted drive. Scans keep its items as they are until it is back.',
		not_mounted:
			"Not on a mounted drive: it's inside the container, where nothing from the host is.",
		not_connected:
			'Scans keep its items as they are and try again; it is also retried every few minutes.'
	};
	const scanText = {
		started: 'a scan started',
		queued: 'a scan is queued',
		already_queued: 'a waiting scan covers it'
	};
	// The SMB form (SmbRequest with every field a string).
	type SmbForm = {
		share: string;
		username: string;
		password: string;
		domain: string;
		options: string;
	};
	const emptySmb = (): SmbForm => ({
		share: '',
		username: '',
		password: '',
		domain: '',
		options: ''
	});
	const label = (s: MediaSourceInfo) => s.smb?.share ?? s.path;

	let sources = $state<MediaSourceInfo[] | null>(null);
	let smbSupport = $state<SmbSupport | null>(null);
	let media = $state<Media>('comic');
	// 0: a folder, 1: an SMB share
	let addKind = $state(0);
	let path = $state('');
	let newSmb = $state<SmbForm>(emptySmb());
	let adding = $state(false);
	let addError = $state('');
	let removing = $state<MediaSourceInfo | null>(null);
	let removeBusy = $state(false);
	let connecting = $state<number | null>(null);
	let editing = $state<MediaSourceInfo | null>(null);
	let editSmb = $state<SmbForm>(emptySmb());
	let editBusy = $state(false);
	let editError = $state('');
	let picker = $state<FolderListing | null>(null);
	let pickerOpen = $state(false);
	let pickerError = $state('');

	const canAdd = $derived(
		addKind === 0 ? !!path.trim() : !!newSmb.share.trim() && !!smbSupport?.supported
	);

	const errorMsg = (error: unknown, fallback: string) =>
		error && typeof error === 'object' && 'msg' in error && typeof error.msg === 'string'
			? error.msg
			: fallback;

	async function load() {
		const { data, error } = await SystemService.listMediaSources();
		if (!error && data) sources = data;
	}

	async function loadSmbSupport() {
		const { data, error } = await SystemService.smbSupport();
		if (!error && data) smbSupport = data;
	}

	async function add() {
		if (!canAdd) return;
		adding = true;
		addError = '';
		const body =
			addKind === 0
				? { media, kind: 'local' as const, path }
				: { media, kind: 'smb' as const, smb: newSmb };
		const { data, error } = await SystemService.addMediaSource({ body });
		adding = false;
		if (error || !data) {
			addError = errorMsg(error, "Couldn't add it");
			return;
		}
		path = '';
		newSmb = emptySmb();
		addNotification(
			new SuccessNotification({
				subtitle: `Added ${label(data.source)}; ${scanText[data.scan]}`
			})
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
				new ErrorNotification({ subtitle: errorMsg(error, `Couldn't remove ${label(source)}`) })
			);
			return;
		}
		addNotification(
			new SuccessNotification({ subtitle: `Removed ${label(source)}; ${scanText[data.scan]}` })
		);
		await load();
		onscan?.();
	}

	async function reconnect(source: MediaSourceInfo) {
		if (source.id == null) return;
		connecting = source.id;
		const { data, error } = await SystemService.connectMediaSource({ path: { id: source.id } });
		connecting = null;
		if (error || !data) {
			addNotification(
				new ErrorNotification({ subtitle: errorMsg(error, `Couldn't reconnect ${label(source)}`) })
			);
		} else if (data.status === 'ok') {
			addNotification(new SuccessNotification({ subtitle: `Connected ${label(data)}` }));
		} else {
			addNotification(
				new ErrorNotification({ subtitle: `${label(data)} not connected: ${data.error ?? ''}` })
			);
		}
		await load();
	}

	function startEdit(source: MediaSourceInfo) {
		editError = '';
		editSmb = {
			share: source.smb?.share ?? '',
			username: source.smb?.username ?? '',
			password: '',
			domain: source.smb?.domain ?? '',
			options: source.smb?.options ?? ''
		};
		editing = source;
	}

	async function saveEdit() {
		const source = editing;
		if (source?.id == null) return;
		editBusy = true;
		editError = '';
		const { data, error } = await SystemService.updateMediaSource({
			path: { id: source.id },
			body: editSmb
		});
		editBusy = false;
		if (error || !data) {
			editError = errorMsg(error, "Couldn't save the share");
			return;
		}
		editing = null;
		addNotification(new SuccessNotification({ subtitle: `Saved and connected ${label(data)}` }));
		await load();
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

	onMount(() => {
		load();
		loadSmbSupport();
	});
</script>

{#snippet smbFields(f: SmbForm, passwordHint: string)}
	<div class="smb-fields">
		<TextInput
			size="sm"
			labelText="Share"
			placeholder="\\server\share\folder"
			helperText="//server/share works too; a folder after the share is optional"
			bind:value={f.share}
		/>
		<TextInput
			size="sm"
			labelText="User name"
			placeholder="Empty for guest access"
			bind:value={f.username}
		/>
		<PasswordInput
			size="sm"
			labelText="Password"
			placeholder={passwordHint}
			autocomplete="new-password"
			bind:value={f.password}
		/>
		<TextInput size="sm" labelText="Domain (optional)" bind:value={f.domain} />
		<TextInput
			size="sm"
			labelText="Mount options (optional)"
			placeholder="vers=2.0"
			helperText="Extra mount.cifs options, comma-separated"
			bind:value={f.options}
		/>
	</div>
{/snippet}

<Tile class="card">
	<div class="card-head">
		<h3>Media sources</h3>
	</div>
	<p class="muted note">
		Folders scanned for each media type. Built-in ones come from compose.yaml; added folders must be
		inside a drive or share mounted there, and SMB shares are mounted by the app itself. A source
		that is missing, empty or not connected keeps its items as they are until it's back.
	</p>
	{#each medias as m (m.id)}
		{@const rows = sources?.filter((s) => s.media === m.id) ?? []}
		<h4>{m.text}</h4>
		<ul class="sources">
			{#each rows as source (source.id ?? source.path)}
				<li>
					<div class="row">
						{#if source.kind === 'smb'}<Network_3 size={16} class="kind-icon" />{/if}
						<span
							class="path"
							title={source.kind === 'smb' ? `Mounted at ${source.path}` : source.path}
							>{label(source)}</span
						>
						{#if source.status !== 'ok'}
							<Tag
								type={source.status === 'not_mounted' ? 'warm-gray' : 'red'}
								size="sm"
								title={statusHint[source.status]}>{statusText[source.status]}</Tag
							>
						{/if}
						{#if source.builtin}
							<Tag type="gray" size="sm">Built-in</Tag>
						{:else}
							{#if source.kind === 'smb'}
								<Button
									kind="ghost"
									size="small"
									icon={Renew}
									iconDescription="Reconnect"
									disabled={connecting === source.id}
									on:click={() => reconnect(source)}
								/>
								<Button
									kind="ghost"
									size="small"
									icon={Edit}
									iconDescription="Edit"
									on:click={() => startEdit(source)}
								/>
							{/if}
							<Button
								kind="ghost"
								size="small"
								icon={TrashCan}
								iconDescription="Remove"
								on:click={() => (removing = source)}
							/>
						{/if}
					</div>
					{#if source.error}
						<div class="err source-error">{source.error}</div>
					{/if}
				</li>
			{:else}
				<li class="muted">{sources ? 'None' : 'Loading…'}</li>
			{/each}
		</ul>
	{/each}

	<h4>Add a source</h4>
	<ContentSwitcher size="sm" bind:selectedIndex={addKind}>
		<Switch text="Folder" />
		<Switch text="SMB share" />
	</ContentSwitcher>
	<div class="add">
		<Dropdown
			size="sm"
			titleText="Media"
			label="Media"
			hideLabel={addKind === 0}
			items={medias}
			bind:selectedId={media}
		/>
		{#if addKind === 0}
			<TextInput
				size="sm"
				labelText="Folder"
				hideLabel
				placeholder="/data/…"
				bind:value={path}
				on:keydown={(e) => {
					if (e.key === 'Enter') add();
				}}
			/>
		{/if}
	</div>
	{#if addKind === 1}
		{#if smbSupport && !smbSupport.supported}
			<InlineNotification
				kind="info"
				lowContrast
				hideCloseButton
				title="SMB shares can't be mounted here:"
				subtitle={smbSupport.reason ?? ''}
			/>
		{/if}
		{@render smbFields(newSmb, '')}
	{/if}
	<div class="add-actions">
		{#if addKind === 0}
			<Button kind="secondary" size="small" icon={Folder} on:click={openPicker}>Browse</Button>
		{/if}
		<Button size="small" icon={Add} disabled={adding || !canAdd} on:click={add}
			>{adding && addKind === 1 ? 'Connecting…' : 'Add'}</Button
		>
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
		Stop scanning <code>{removing ? label(removing) : ''}</code>?
		{removing?.kind === 'smb'
			? 'The share is unmounted; nothing on it changes.'
			: 'Nothing on disk changes.'}
		The scan that follows lists its comics and videos under Cleanup → Missing files and drops its image
		albums; adding it again brings them back.
	</p>
</Modal>

<Modal
	open={editing !== null}
	modalHeading="Edit SMB share"
	primaryButtonText={editBusy ? 'Connecting…' : 'Save and reconnect'}
	primaryButtonDisabled={editBusy || !editSmb.share.trim()}
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (editing = null)}
	on:close={() => (editing = null)}
	on:submit={saveEdit}
>
	<p class="muted note">
		The share is mounted again with these settings; if that fails, the current ones stay.
	</p>
	{@render smbFields(
		editSmb,
		editing?.smb?.hasPassword ? 'Unchanged (leave empty to keep it)' : 'No password saved'
	)}
	{#if editError}
		<InlineNotification
			kind="error"
			lowContrast
			hideCloseButton
			title="Not saved:"
			subtitle={editError}
		/>
	{/if}
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
		font-size: 0.875rem;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 2rem;
	}

	.row :global(.kind-icon) {
		flex: none;
	}

	.err {
		color: var(--cds-support-error, #fa4d56);
	}

	.source-error {
		font-size: 0.75rem;
		padding-bottom: 0.25rem;
		overflow-wrap: anywhere;
	}

	.smb-fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
		gap: 0.75rem 1rem;
	}

	.smb-fields > :global(:first-child) {
		grid-column: 1 / -1;
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
