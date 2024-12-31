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
		Content
	} from 'carbon-components-svelte';
	import SettingsAdjust from 'carbon-icons-svelte/lib/SettingsAdjust.svelte';
	import UserAvatarFilledAlt from 'carbon-icons-svelte/lib/UserAvatarFilledAlt.svelte';
	import SettingsModal from './SettingsModal.svelte';
	let openSettingsModal = false;
	let isOpen1 = false;
	let isOpen2 = false;

	function onClickSettings(e: MouseEvent): void {
		openSettingsModal = true;
	}
</script>

<Header platformName="Organizer" href="/">
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
				<HeaderPanelDivider>Comics</HeaderPanelDivider>
				<HeaderPanelLink href="/comic">Home</HeaderPanelLink>
				<HeaderPanelDivider>Videos</HeaderPanelDivider>
				<HeaderPanelLink href="/video">Home</HeaderPanelLink>
				<HeaderPanelDivider>Images</HeaderPanelDivider>
				<HeaderPanelLink href="/image">Home</HeaderPanelLink>
			</HeaderPanelLinks>
		</HeaderAction>
	</HeaderUtilities>
</Header>

<Content style="padding-left:0%;padding-right:0%;padding-top:0.5rem">
	<slot />
</Content>

<SettingsModal open={openSettingsModal} onCloseModal={() => (openSettingsModal = false)} />

<style>
</style>
