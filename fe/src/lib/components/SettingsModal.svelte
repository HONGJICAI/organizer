<script lang="ts">
	import { config, PageWidthMode, savePrefs } from '$lib/config.svelte';
	import { connect } from '$lib/connection.svelte';
	import { ContentSwitcher, Modal, NumberInput, Switch, TextInput } from 'carbon-components-svelte';
	import { FitToHeight, FitToScreen, FitToWidth, ArrowsVertical } from 'carbon-icons-svelte';

	interface Props {
		open?: boolean;
		onCloseModal?: () => void;
	}
	let { open = $bindable(false), onCloseModal = () => undefined }: Props = $props();
	let apiServer = $state(config.apiServer),
		staticServer = $state(config.staticServer),
		viewMode = $state(config.viewMode),
		pageWidthMode = $state(config.pageWidthMode),
		pageWidthCustom = $state(config.pageWidthCustom);
</script>

<Modal
	size="lg"
	bind:open
	modalHeading="Settings"
	primaryButtonText="Save"
	secondaryButtonText="Cancel"
	on:click:button--secondary={onCloseModal}
	on:open
	on:close={onCloseModal}
	on:submit={() => {
		// A new API server goes through the connect flow, which checks it and
		// remembers it for the next visit.
		if (apiServer && apiServer !== config.apiServer) connect(apiServer);
		config.staticServer = staticServer;
		config.viewMode = viewMode;
		config.pageWidthMode = pageWidthMode;
		config.pageWidthCustom = pageWidthCustom;
		savePrefs();
		open = false;
	}}
>
	<h>Server</h>
	<TextInput labelText="API Server" bind:value={apiServer} />
	<TextInput
		labelText="Static Server"
		placeholder={config.apiServer || 'Same as API server'}
		helperText="Where covers load from. Leave empty to use the API server."
		bind:value={staticServer}
	/>
	<h>Read</h>
	<div>
		<ContentSwitcher bind:selectedIndex={viewMode}>
			<Switch>
				<div class="switch-label"><FitToWidth /><span>Width</span></div>
			</Switch>
			<Switch>
				<div class="switch-label"><FitToHeight /><span>Height</span></div>
			</Switch>
			<Switch>
				<div class="switch-label"><FitToScreen /><span>Contain</span></div>
			</Switch>
			<Switch>
				<div class="switch-label"><ArrowsVertical /><span>Scroll</span></div>
			</Switch>
		</ContentSwitcher>
	</div>
	<h>Page Width</h>
	<div>
		<ContentSwitcher bind:selectedIndex={pageWidthMode}>
			<Switch>
				<div class="switch-label"><span>Original</span></div>
			</Switch>
			<Switch>
				<div class="switch-label"><span>Device</span></div>
			</Switch>
			<Switch>
				<div class="switch-label"><span>Custom</span></div>
			</Switch>
		</ContentSwitcher>
		{#if pageWidthMode === PageWidthMode.Custom}
			<NumberInput
				label="Custom width (px)"
				min={1}
				max={4096}
				step={10}
				bind:value={pageWidthCustom}
			/>
		{/if}
	</div>
</Modal>

<style>
	.switch-label {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
	}
</style>
