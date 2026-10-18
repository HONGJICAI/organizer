<script lang="ts">
	import {
		Header,
		HeaderUtilities,
		HeaderAction,
		HeaderGlobalAction,
		HeaderPanelLinks,
		HeaderPanelDivider,
		HeaderPanelLink,
		SkipToContent,
		Content,
		ToastNotification
	} from 'carbon-components-svelte';
	import SettingsAdjust from 'carbon-icons-svelte/lib/SettingsAdjust.svelte';
	import Menu from 'carbon-icons-svelte/lib/Menu.svelte';
	import Close from 'carbon-icons-svelte/lib/Close.svelte';
	import SearchIcon from 'carbon-icons-svelte/lib/Search.svelte';
	import ViewOff from 'carbon-icons-svelte/lib/ViewOff.svelte';
	import View from 'carbon-icons-svelte/lib/View.svelte';
	import Information from 'carbon-icons-svelte/lib/Information.svelte';
	import { config, savePrefs } from '$lib/config.svelte';
	import { formatBytes } from '$lib/stats';
	import { goto } from '$app/navigation';
	import SettingsModal from './SettingsModal.svelte';
	import { notifications } from '$lib/state.svelte';
	import { setPrivateReading, viewerState } from '$lib/viewerState.svelte';
	import { authState } from '$lib/auth.svelte';
	import Logout from 'carbon-icons-svelte/lib/Logout.svelte';
	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();
	let openSettingsModal = $state(false);
	let isOpen2 = $state(false);

	function onClickSettings(): void {
		openSettingsModal = true;
	}
</script>

<Header platformName="Organizer" href="/">
	<!-- @migration-task: migrate this slot by hand, `skip-to-content` is an invalid identifier -->
	<svelte:fragment slot="skip-to-content">
		<SkipToContent />
	</svelte:fragment>

	{#if viewerState.active}
		<div class="viewer-center">
			<span class="viewer-title">{viewerState.title}</span>
			{#if viewerState.maxPage > 0}
				<button
					class="viewer-page"
					class:active={viewerState.overviewOpen}
					title="Page overview"
					aria-label="Toggle page overview"
					onclick={() => (viewerState.overviewOpen = !viewerState.overviewOpen)}
				>
					{viewerState.page} / {viewerState.maxPage}
				</button>
			{/if}
			{#if viewerState.maxPage > 0 && viewerState.pageDetails.length > 0}
				{@const info = viewerState.pageDetails[viewerState.page - 1]}
				{@const dims = viewerState.pageInfos[viewerState.page]}
				<button
					class="viewer-info"
					class:open={config.showPageInfo}
					title={config.showPageInfo ? 'Hide page info' : 'Show page file name and size'}
					aria-label={config.showPageInfo ? 'Hide page info' : 'Show page info'}
					aria-pressed={config.showPageInfo}
					onclick={() => {
						config.showPageInfo = !config.showPageInfo;
						savePrefs();
					}}
				>
					<Information size={16} />
					{#if config.showPageInfo && info}
						<span class="viewer-info-detail">
							<span class="viewer-info-name" title={info.name}>{info.name}</span>
							{#if dims}<span>· {dims.width}×{dims.height} {dims.format}</span>{/if}
							<span>· {formatBytes(info.size)}</span>
						</span>
					{/if}
				</button>
			{/if}
			{#if viewerState.maxPage > 0}
				<button
					class="viewer-private"
					class:on={viewerState.privateReading}
					title={viewerState.privateReading
						? "Reading progress isn't being saved. Click to start saving it."
						: 'Read privately: stop saving reading progress for this session.'}
					aria-label="Private reading"
					aria-pressed={viewerState.privateReading}
					onclick={() => setPrivateReading(!viewerState.privateReading)}
				>
					{#if viewerState.privateReading}
						<ViewOff size={16} /><span class="viewer-private-label">Private</span>
					{:else}
						<View size={16} />
					{/if}
				</button>
			{/if}
		</div>
	{/if}

	<HeaderUtilities>
		{#if !viewerState.active}
			<HeaderGlobalAction
				aria-label={viewerState.privateSession
					? 'Private reading on: progress is not saved. Click to turn off.'
					: 'Private reading off. Click to stop saving progress for this session.'}
				icon={viewerState.privateSession ? ViewOff : View}
				isActive={viewerState.privateSession}
				on:click={() => setPrivateReading(!viewerState.privateSession)}
			/>
			<HeaderGlobalAction aria-label="Search" icon={SearchIcon} on:click={() => goto('/search')} />
		{/if}
		<HeaderGlobalAction aria-label="Settings" icon={SettingsAdjust} on:click={onClickSettings} />
		{#if authState.required}
			<HeaderGlobalAction
				aria-label="Logout"
				icon={Logout}
				on:click={() => authState.clearToken()}
			/>
		{/if}
		{#if viewerState.active}
			<HeaderGlobalAction aria-label="Close" icon={Close} on:click={() => viewerState.onClose()} />
		{:else}
			<HeaderAction bind:isOpen={isOpen2} icon={Menu} closeIcon={Menu}>
				<HeaderPanelLinks>
					<HeaderPanelLink href="/">Home</HeaderPanelLink>
					<HeaderPanelDivider>Comics</HeaderPanelDivider>
					<HeaderPanelLink href="/comic">Home</HeaderPanelLink>
					<HeaderPanelLink href="/comic/folder">Folder</HeaderPanelLink>
					<HeaderPanelLink href="/comic/tag">Tag</HeaderPanelLink>
					<HeaderPanelLink href="/comic/organize">Organize</HeaderPanelLink>
					<HeaderPanelLink href="/comic/duplicates">Duplicates</HeaderPanelLink>
					<HeaderPanelLink href="/stats">Stats</HeaderPanelLink>
					<HeaderPanelDivider>Videos</HeaderPanelDivider>
					<HeaderPanelLink href="/video">Home</HeaderPanelLink>
					<HeaderPanelLink href="/video/folder">Folder</HeaderPanelLink>
					<HeaderPanelLink href="/video/tag">Tag</HeaderPanelLink>
					<HeaderPanelDivider>Images</HeaderPanelDivider>
					<HeaderPanelLink href="/image">Home</HeaderPanelLink>
					<HeaderPanelLink href="/image/folder">Folder</HeaderPanelLink>
					<HeaderPanelLink href="/image/tag">Tag</HeaderPanelLink>
					<HeaderPanelDivider>System</HeaderPanelDivider>
					<HeaderPanelLink href="/admin">Admin</HeaderPanelLink>
				</HeaderPanelLinks>
			</HeaderAction>
		{/if}
	</HeaderUtilities>
</Header>

<Content style="padding-left:0;padding-right:0;padding-top:0">
	{@render children?.()}
</Content>

{#if openSettingsModal}
	<SettingsModal open={openSettingsModal} onCloseModal={() => (openSettingsModal = false)} />
{/if}

{#if notifications.length > 0}
	<div class="notification-stack">
		{#each notifications as notification}
			<ToastNotification
				timeout={notification.timeout}
				kind={notification.kind}
				title={notification.title}
				subtitle={notification.subtitle}
				caption={notification.caption}
				on:close={() => {
					const idx = notifications.indexOf(notification);
					notifications.splice(idx, 1);
				}}
			/>
		{/each}
	</div>
{/if}

<style>
	.viewer-center {
		position: absolute;
		left: 50%;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		gap: 0.625rem;
		max-width: calc(100vw - 8rem);
		pointer-events: none;
	}

	.viewer-title {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.875rem;
		color: var(--cds-text-02, #c6c6c6);
	}

	.viewer-page {
		flex-shrink: 0;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-01, #f4f4f4);
		background: var(--cds-ui-04, #8d8d8d);
		padding: 0.125rem 0.5rem;
		border-radius: 1rem;
		/* Re-enable clicks: the centered container disables pointer events so it
		   never blocks the header buttons behind it. */
		pointer-events: auto;
		border: none;
		cursor: pointer;
	}

	.viewer-page.active {
		background: var(--cds-interactive-01, #0f62fe);
		color: var(--cds-text-04, #ffffff);
	}

	.viewer-private {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		color: var(--cds-text-02, #c6c6c6);
		background: none;
		padding: 0.125rem 0.375rem;
		border: 1px solid transparent;
		border-radius: 1rem;
		pointer-events: auto;
		cursor: pointer;
	}

	.viewer-private.on {
		color: var(--cds-text-01, #f4f4f4);
		padding: 0.125rem 0.5rem;
		border-color: var(--cds-ui-04, #8d8d8d);
	}

	.viewer-info {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
		max-width: 22rem;
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		color: var(--cds-text-02, #c6c6c6);
		background: none;
		border: 1px solid transparent;
		border-radius: 1rem;
		pointer-events: auto;
		cursor: pointer;
	}

	.viewer-info.open {
		color: var(--cds-text-01, #f4f4f4);
		border-color: var(--cds-ui-04, #8d8d8d);
	}

	.viewer-info-detail {
		display: inline-flex;
		gap: 0.25rem;
		min-width: 0;
	}

	.viewer-info-name {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* On narrow screens the header has room for little besides the page
	   counter (which doubles as the overview entry point): drop the title and
	   the "Organizer" name (the close button leaves the reader), shrink the
	   chips to icons, and show the page info in a strip below the header. */
	@media screen and (max-width: 672px) {
		.viewer-title,
		.viewer-private-label {
			display: none;
		}

		:global(.bx--header:has(.viewer-center) .bx--header__name) {
			display: none;
		}

		.viewer-info {
			flex-shrink: 0;
			max-width: none;
		}

		.viewer-info-detail {
			position: absolute;
			top: calc(100% + 0.75rem);
			left: 50%;
			transform: translateX(-50%);
			max-width: calc(100vw - 1rem);
			padding: 0.25rem 0.625rem;
			border-radius: 1rem;
			background: rgba(22, 22, 22, 0.85);
			color: var(--cds-text-01, #f4f4f4);
			pointer-events: none;
		}
	}

	.notification-stack {
		position: fixed;
		top: 3rem;
		right: 0;
		z-index: 9999;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
</style>
