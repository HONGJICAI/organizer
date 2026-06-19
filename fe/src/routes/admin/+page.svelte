<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SystemService } from '$lib/client';
	import type { ScanStatusResponse, TasksResponse } from '$lib/client';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		ProgressBar,
		Tag,
		Tile
	} from 'carbon-components-svelte';
	import { Home, Renew } from 'carbon-icons-svelte';

	let scan = $state<ScanStatusResponse | null>(null);
	let tasks = $state<TasksResponse | null>(null);
	let triggering = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;
	let wasRunning = false;

	function fmtTime(iso: string | null | undefined): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString();
	}

	function fmtMs(ms: number): string {
		return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
	}

	function fmtDuration(s: number | null | undefined): string {
		if (s == null) return '—';
		if (s < 60) return `${s.toFixed(1)}s`;
		const m = Math.floor(s / 60);
		return `${m}m ${Math.round(s % 60)}s`;
	}

	async function loadScan() {
		const { data, error } = await SystemService.scanStatus();
		if (!error && data) scan = data;
		return scan?.running ?? false;
	}

	async function loadTasks() {
		const { data, error } = await SystemService.tasksStatus();
		if (!error && data) tasks = data;
	}

	// Poll faster while a scan is in flight, slow to a heartbeat when idle, so
	// the metrics stay live without hammering the backend.
	async function poll() {
		const running = await loadScan();
		if (wasRunning && !running) {
			// A scan just finished; it may have imported or reconciled away media, so
			// drop the cached lists to force a re-fetch on the next visit (mediaStore).
			refreshMediaFiles();
		}
		wasRunning = running;
		timer = setTimeout(poll, running ? 1000 : 5000);
	}

	async function triggerScan() {
		triggering = true;
		const { data, error } = await SystemService.triggerScan({ query: { media_type: 'all' } });
		triggering = false;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to start scan' }));
			return;
		}
		if (data.status === 'already_running') {
			addNotification(new SuccessNotification({ subtitle: 'A scan is already running' }));
		} else {
			addNotification(new SuccessNotification({ subtitle: 'Scan started' }));
		}
		clearTimeout(timer);
		poll();
		loadTasks();
	}

	onMount(() => {
		poll();
		loadTasks();
	});

	onDestroy(() => clearTimeout(timer));

	let lastStatus = $derived(scan?.last_result?.status as string | undefined);
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/">
		<span class="crumb"><Home size={16} /><span>Home</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Admin</BreadcrumbItem>
</Breadcrumb>
<h1>System</h1>

<div class="grid">
	<Tile class="card">
		<div class="card-head">
			<h3>Media scan</h3>
			{#if scan?.running}
				<Tag type="blue">Running</Tag>
			{:else if lastStatus === 'error'}
				<Tag type="red">Last run failed</Tag>
			{:else if lastStatus === 'success'}
				<Tag type="green">Idle</Tag>
			{:else}
				<Tag type="gray">Idle</Tag>
			{/if}
		</div>

		{#if scan?.running}
			<p class="phase">
				Phase: <strong>{scan.phase ?? '…'}</strong>
				{#if scan.media_type}<span class="muted"> ({scan.media_type})</span>{/if}
			</p>
			<ProgressBar
				value={scan.processed}
				max={scan.total || undefined}
				labelText={`Processed ${scan.processed ?? 0}${scan.total ? ` / ${scan.total}` : ''}`}
				helperText={scan.total ? undefined : 'Counting…'}
			/>
		{:else}
			<dl class="kv">
				<dt>Last result</dt>
				<dd>{lastStatus ?? '— never run —'}</dd>
				{#if scan?.last_result?.message}
					<dt>Message</dt>
					<dd class="err">{scan.last_result.message}</dd>
				{/if}
				<dt>Finished</dt>
				<dd>{fmtTime(scan?.finished_at)}</dd>
			</dl>
		{/if}

		<dl class="kv">
			<dt>Started</dt>
			<dd>{fmtTime(scan?.started_at)}</dd>
			<dt>Duration</dt>
			<dd>{fmtDuration(scan?.duration_seconds)}</dd>
			<dt>Missing reconciled</dt>
			<dd>{scan?.reconciled ?? 0}</dd>
		</dl>

		<Button icon={Renew} disabled={triggering || scan?.running} on:click={triggerScan}>
			{scan?.running ? 'Scan in progress…' : 'Scan now'}
		</Button>
	</Tile>

	<Tile class="card">
		<div class="card-head"><h3>Open timing</h3></div>
		<p class="muted">
			Per-file open/parse time during the scan — a climbing p95 is the first sign of a flaky network
			mount.
		</p>
		<dl class="kv">
			<dt>Files timed</dt>
			<dd>{scan?.timing.count ?? 0}</dd>
			<dt>Average</dt>
			<dd>{fmtMs(scan?.timing.avg_ms ?? 0)}</dd>
			<dt>p95</dt>
			<dd>{fmtMs(scan?.timing.p95_ms ?? 0)}</dd>
		</dl>
		{#if scan?.timing.slowest?.length}
			<h4>Slowest files</h4>
			<ul class="slow">
				{#each scan.timing.slowest as f}
					<li>
						<span class="slow-ms">{fmtMs(f.ms)}</span><span class="slow-path" title={f.path}
							>{f.path}</span
						>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="muted">No timing samples yet.</p>
		{/if}
	</Tile>

	<Tile class="card">
		<div class="card-head"><h3>Background tasks</h3></div>
		<dl class="kv">
			<dt>Next daily scan</dt>
			<dd>
				{fmtTime(tasks?.daily_scan.next_run)}
				<span class="muted">({String(tasks?.daily_scan.scan_hour ?? '—').padStart(2, '0')}:00)</span
				>
			</dd>
			<dt>Last backup</dt>
			<dd>{fmtTime(tasks?.backup.last_backup)}</dd>
			<dt>Backups kept</dt>
			<dd>
				{tasks?.backup.backup_count ?? 0}
				<span class="muted">(every {tasks?.backup.cadence_hours ?? 24}h)</span>
			</dd>
		</dl>
	</Tile>
</div>

<style>
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
		gap: 1rem;
		padding: 0 1rem 2rem;
	}

	:global(.card) {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.card-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.card-head h3 {
		margin: 0;
	}

	.kv {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.25rem 1rem;
		margin: 0;
		font-size: 0.875rem;
	}

	.kv dt {
		color: var(--cds-text-02, #c6c6c6);
	}

	.kv dd {
		margin: 0;
		font-variant-numeric: tabular-nums;
	}

	.muted {
		color: var(--cds-text-02, #c6c6c6);
	}

	.err {
		color: var(--cds-support-error, #fa4d56);
	}

	.phase {
		margin: 0;
		font-size: 0.875rem;
	}

	h4 {
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
	}

	.slow {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.8125rem;
	}

	.slow li {
		display: flex;
		gap: 0.5rem;
		align-items: baseline;
	}

	.slow-ms {
		flex-shrink: 0;
		width: 4rem;
		text-align: right;
		font-variant-numeric: tabular-nums;
		color: var(--cds-text-01, #f4f4f4);
	}

	.slow-path {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--cds-text-02, #c6c6c6);
	}
</style>
