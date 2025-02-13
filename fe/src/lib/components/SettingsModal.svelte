<script>
	import { config } from '$lib/config.svelte';
	import { ContentSwitcher, Modal, Switch, TextInput } from 'carbon-components-svelte';
	import { FitToHeight, FitToScreen, FitToWidth } from 'carbon-icons-svelte';

	/** @type {{open?: boolean, onCloseModal?: any}} */
	let { open = $bindable(false), onCloseModal = () => {} } = $props();
	let apiServer = $state(config.apiServer),
		staticServer = $state(config.staticServer),
		viewMode = $state(config.viewMode);
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
		config.apiServer = apiServer;
		config.staticServer = staticServer;
		config.viewMode = viewMode;
		open = false;
	}}
>
	<h>Server</h>
	<TextInput labelText="API Server" value={apiServer} />
	<TextInput labelText="Static Server" value={staticServer} />
	<h>Read</h>
	<container>
		<ContentSwitcher bind:selectedIndex={viewMode}>
			<Switch>
				<div style="display: flex; align-items: center;">
					<FitToWidth style="margin-right: 0.5rem;" />
				</div>
			</Switch>
			<Switch>
				<div style="display: flex; align-items: center;">
					<FitToHeight style="margin-right: 0.5rem;" />
				</div>
			</Switch>
			<Switch disabled>
				<div style="display: flex; align-items: center;">
					<FitToScreen style="margin-right: 0.5rem;" />
				</div>
			</Switch>
		</ContentSwitcher>
	</container>
</Modal>
