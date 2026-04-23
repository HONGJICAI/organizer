<script lang="ts">
	import {
		Button,
		InlineNotification,
		InlineLoading,
		PasswordInput
	} from 'carbon-components-svelte';
	import SettingsAdjust from 'carbon-icons-svelte/lib/SettingsAdjust.svelte';
	import SettingsModal from './SettingsModal.svelte';
	import { authState } from '$lib/auth.svelte';
	import { config } from '$lib/config.svelte';

	let password = $state('');
	let loading = $state(false);
	let error = $state('');
	let openSettings = $state(false);

	async function submit() {
		if (!password || loading) return;
		loading = true;
		error = '';
		try {
			const r = await fetch(`${config.apiServer}/api/auth/login`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ password })
			});
			if (r.status === 401) {
				error = 'Invalid password';
				return;
			}
			if (!r.ok) {
				error = 'Server error, please try again';
				return;
			}
			const { token } = await r.json();
			authState.setToken(token);
		} catch {
			error = 'Could not reach server';
		} finally {
			loading = false;
		}
	}
</script>

<div class="login-root">
	<button class="settings-btn" aria-label="Settings" onclick={() => (openSettings = true)}>
		<SettingsAdjust size={20} />
	</button>
	<div class="login-card">
		<h2 class="login-title">Organizer</h2>
		<form
			class="login-form"
			onsubmit={(e) => {
				e.preventDefault();
				submit();
			}}
		>
			<PasswordInput
				labelText="Password"
				placeholder="Admin password"
				bind:value={password}
				disabled={loading}
			/>
			{#if error}
				<InlineNotification kind="error" subtitle={error} hideCloseButton lowContrast />
			{/if}
			{#if loading}
				<InlineLoading description="Signing in…" />
			{:else}
				<Button type="submit" disabled={!password} style="width:100%;max-width:none">
					Sign in
				</Button>
			{/if}
		</form>
	</div>
</div>

{#if openSettings}
	<SettingsModal open={openSettings} onCloseModal={() => (openSettings = false)} />
{/if}

<style>
	.login-root {
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

	.login-card {
		background: var(--cds-ui-01, #262626);
		padding: 2rem;
		width: 100%;
		max-width: 20rem;
	}

	.login-title {
		font-size: 1.5rem;
		font-weight: 400;
		margin-bottom: 1.5rem;
		color: var(--cds-text-01, #f4f4f4);
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
</style>
