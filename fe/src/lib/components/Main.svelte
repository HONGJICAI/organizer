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
	import { goto } from '$app/navigation';
	import SettingsModal from './SettingsModal.svelte';
	import { notifications } from '$lib/state.svelte';
	import { viewerState } from '$lib/viewerState.svelte';
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
		</div>
	{/if}

	<HeaderUtilities>
		{#if !viewerState.active}
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

	/* On narrow screens the title eats the header; drop it and keep only the
	   page counter (which doubles as the overview entry point). */
	@media screen and (max-width: 672px) {
		.viewer-title {
			display: none;
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
