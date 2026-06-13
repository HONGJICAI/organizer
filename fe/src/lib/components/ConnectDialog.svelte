<script lang="ts">
	import { onMount } from 'svelte';
	import { Button, TextInput, InlineNotification, InlineLoading } from 'carbon-components-svelte';
	import SettingsAdjust from 'carbon-icons-svelte/lib/SettingsAdjust.svelte';
	import SettingsModal from './SettingsModal.svelte';
	import { connectionState, connect, connectMock, SERVER_URL_KEY } from '$lib/connection.svelte';

	let serverUrl = $state('');
	let openSettings = $state(false);

	// Hidden in the Docker image (built with VITE_HIDE_MOCK=1); shown by default.
	const showMockButton = import.meta.env.VITE_HIDE_MOCK !== '1';

	onMount(async () => {
		const params = new URLSearchParams(window.location.search);

		if (params.get('mock') === '1') {
			const authRequired = params.get('auth') === '1';
			const ok = await connectMock(authRequired);
			if (ok) {
				const { goto, invalidateAll } = await import('$app/navigation');
				await goto('/', { replaceState: true });
				await invalidateAll();
			}
			return;
		}

		const saved = localStorage.getItem(SERVER_URL_KEY);
		serverUrl = saved ?? window.location.origin;
		if (saved !== null) {
			const ok = await connect(saved);
			if (ok) {
				const { invalidateAll } = await import('$app/navigation');
				await invalidateAll();
			}
		}
	});

	async function handleConnect() {
		const ok = await connect(serverUrl);
		if (ok) {
			const { invalidateAll } = await import('$app/navigation');
			await invalidateAll();
		}
	}

	async function handleMock() {
		const ok = await connectMock(false);
		if (ok) {
			const { goto, invalidateAll } = await import('$app/navigation');
			await goto('/', { replaceState: true });
			await invalidateAll();
		}
	}
</script>

<div class="connect-root">
	<button class="settings-btn" aria-label="Settings" onclick={() => (openSettings = true)}>
		<SettingsAdjust size={20} />
	</button>

	<div class="connect-card">
		<h2 class="connect-title">Organizer</h2>

		{#if connectionState.status === 'connecting'}
			<InlineLoading description="Connecting…" />
		{:else}
			<form
				class="connect-form"
				onsubmit={(e) => {
					e.preventDefault();
					handleConnect();
				}}
			>
				<TextInput
					labelText="Server URL"
					placeholder={window.location.origin}
					bind:value={serverUrl}
				/>
				{#if connectionState.error}
					<InlineNotification
						kind="error"
						subtitle={connectionState.error}
						hideCloseButton
						lowContrast
					/>
				{/if}
				<Button type="submit" style="width:100%;max-width:none">Connect</Button>
				{#if showMockButton}
					<Button kind="tertiary" style="width:100%;max-width:none" on:click={handleMock}>
						Try demo (mock data)
					</Button>
				{/if}
			</form>
		{/if}
	</div>
</div>

{#if openSettings}
	<SettingsModal open={openSettings} onCloseModal={() => (openSettings = false)} />
{/if}

<style>
	.connect-root {
		position: fixed;
		inset: 0;
		background: var(--cds-background, #161616);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 9000;
	}

	.settings-btn {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--cds-icon-02, #8d8d8d);
		padding: 0.5rem;
		display: flex;
		align-items: center;
	}

	.settings-btn:hover {
		color: var(--cds-icon-01, #f4f4f4);
	}

	.connect-card {
		background: var(--cds-ui-01, #262626);
		padding: 2rem;
		width: 100%;
		max-width: 24rem;
	}

	.connect-title {
		font-size: 1.5rem;
		font-weight: 400;
		margin-bottom: 1.5rem;
		color: var(--cds-text-01, #f4f4f4);
	}

	.connect-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
</style>
