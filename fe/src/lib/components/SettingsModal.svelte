<script>
	import { config } from '$lib/config';
	import {
		ContentSwitcher,
		Modal,
		Switch,
		TextInput
	} from 'carbon-components-svelte';
	import { FitToHeight, FitToScreen, FitToWidth } from 'carbon-icons-svelte';

	/** @type {{open?: boolean, onCloseModal?: any}} */
	let { open = $bindable(false), onCloseModal = () => {} } = $props();
</script>

<Modal
	size="lg"
	bind:open
	modalHeading="Settings"
	primaryButtonText="Save"
	secondaryButtonText="Cancel"
	on:click:button--secondary
	on:open
	on:close={onCloseModal}
	on:submit
>
	<h>Server</h>
	<TextInput labelText="Server" value={config.apiServer}  />
	<container>
		<ContentSwitcher>
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
			<Switch>
				<div style="display: flex; align-items: center;">
					<FitToScreen style="margin-right: 0.5rem;" />
				</div>
			</Switch>
		</ContentSwitcher>
	</container>
</Modal>
