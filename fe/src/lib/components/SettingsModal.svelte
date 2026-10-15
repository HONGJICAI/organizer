<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { config, PageWidthMode, savePrefs } from '$lib/config.svelte';
	import {
		applyServer,
		normalizeServerUrl,
		probeServer,
		SERVER_ERRORS
	} from '$lib/connection.svelte';
	import { ContentSwitcher, Modal, NumberInput, Switch, TextInput } from 'carbon-components-svelte';
	import { FitToHeight, FitToScreen, FitToWidth, ArrowsVertical } from 'carbon-icons-svelte';

	interface Props {
		open?: boolean;
		onCloseModal?: () => void;
	}
	let { open = $bindable(false), onCloseModal = () => undefined }: Props = $props();
	let apiServer = $state(config.apiServer),
		viewMode = $state(config.viewMode),
		pageWidthMode = $state(config.pageWidthMode),
		pageWidthCustom = $state(config.pageWidthCustom);
	let serverError = $state<string | null>(null);
	let checking = $state(false);

	async function save() {
		// A changed API server is checked first, without dropping the current
		// connection: on failure the dialog stays open with the reason.
		if (apiServer.trim() !== config.apiServer) {
			const url = normalizeServerUrl(apiServer);
			if (!url) {
				serverError = SERVER_ERRORS.format;
				return;
			}
			if (url !== config.apiServer) {
				checking = true;
				const probe = await probeServer(url);
				checking = false;
				if (!probe.ok) {
					serverError = probe.error;
					return;
				}
				applyServer(url, probe.required);
				// Re-run the current page's loads against the new server.
				invalidateAll();
			}
			apiServer = url;
		}
		config.viewMode = viewMode;
		config.pageWidthMode = pageWidthMode;
		config.pageWidthCustom = pageWidthCustom;
		savePrefs();
		open = false;
	}
</script>

<Modal
	size="lg"
	bind:open
	modalHeading="Settings"
	primaryButtonText={checking ? 'Checking server…' : 'Save'}
	primaryButtonDisabled={checking}
	secondaryButtonText="Cancel"
	on:click:button--secondary={onCloseModal}
	on:open
	on:close={onCloseModal}
	on:submit={save}
>
	<h>Server</h>
	<TextInput
		labelText="API Server"
		placeholder="https://host:port"
		bind:value={apiServer}
		invalid={serverError !== null}
		invalidText={serverError ?? ''}
		on:input={() => (serverError = null)}
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
