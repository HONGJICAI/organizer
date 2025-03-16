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
	import UserAvatarFilledAlt from 'carbon-icons-svelte/lib/UserAvatarFilledAlt.svelte';
	import SettingsModal from './SettingsModal.svelte';
	import { notifications } from '$lib/state.svelte';
	interface Props {
		children?: import('svelte').Snippet;
	}

	let { children }: Props = $props();
	let openSettingsModal = $state(false);
	let isOpen1 = $state(false);
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
	<HeaderUtilities>
		<HeaderGlobalAction aria-label="Settings" icon={SettingsAdjust} on:click={onClickSettings} />
		<HeaderAction bind:isOpen={isOpen1} icon={UserAvatarFilledAlt} closeIcon={UserAvatarFilledAlt}>
			<HeaderPanelLinks>
				<HeaderPanelDivider>Switcher subject 1</HeaderPanelDivider>
				<HeaderPanelLink>Switcher item 1</HeaderPanelLink>
				<HeaderPanelDivider>Switcher subject 2</HeaderPanelDivider>
				<HeaderPanelLink>Switcher item 1</HeaderPanelLink>
				<HeaderPanelDivider>Switcher subject 3</HeaderPanelDivider>
				<HeaderPanelLink>Switcher item 1</HeaderPanelLink>
			</HeaderPanelLinks>
		</HeaderAction>
		<HeaderAction bind:isOpen={isOpen2}>
			<HeaderPanelLinks>
				<HeaderPanelLink href="/">Home</HeaderPanelLink>
				<HeaderPanelDivider>Comics</HeaderPanelDivider>
				<HeaderPanelLink href="/comic">Home</HeaderPanelLink>
				<HeaderPanelLink href="/comic/tag">Tag</HeaderPanelLink>
				<HeaderPanelLink href="/comic/organize">Organize</HeaderPanelLink>
				<HeaderPanelDivider>Videos</HeaderPanelDivider>
				<HeaderPanelLink href="/video">Home</HeaderPanelLink>
				<HeaderPanelDivider>Images</HeaderPanelDivider>
				<HeaderPanelLink href="/image">Home</HeaderPanelLink>
			</HeaderPanelLinks>
		</HeaderAction>
	</HeaderUtilities>
</Header>

<Content style="padding-left:0%;padding-right:0%;padding-top:0.5rem">
	{@render children?.()}
</Content>

{#if openSettingsModal}
	<SettingsModal open={openSettingsModal} onCloseModal={() => (openSettingsModal = false)} />
{/if}

{#if notifications.length > 0}
	{#each notifications as notification}
		<div class="notification">
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
		</div>
	{/each}
{/if}

<style>
	.notification {
		position: fixed;
		top: 0;
		right: 0;
		z-index: 9999;
	}
</style>
