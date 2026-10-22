<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { ComicsService, SystemService } from '$lib/client';
	import type {
		ComicZipPlanItem,
		CoverRegenStatus,
		JobInfo,
		JobsResponse,
		ScanStatusResponse,
		TasksResponse
	} from '$lib/client';
	import { ErrorNotification, SuccessNotification } from '$lib/model.svelte';
	import { addNotification } from '$lib/state.svelte';
	import { refreshMediaFiles } from '$lib/mediaStore';
	import {
		Breadcrumb,
		BreadcrumbItem,
		Button,
		Dropdown,
		Modal,
		ProgressBar,
		Tag,
		Tile
	} from 'carbon-components-svelte';
	import { Archive, Close, Home, Image as ImageIcon, Renew, Search } from 'carbon-icons-svelte';

	let scan = $state<ScanStatusResponse | null>(null);
	let tasks = $state<TasksResponse | null>(null);
	let triggering = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;
	let wasRunning = false;
	let covers = $state<CoverRegenStatus | null>(null);
	let coversWereRunning = false;
	let confirmCovers = $state(false);
	let startingCovers = $state(false);
	let jobs = $state<JobsResponse | null>(null);
	// What "Scan now" covers; a full scan already includes the single types.
	let scanScope = $state<'all' | 'comics' | 'videos' | 'images'>('all');
	const scanScopes = [
		{ id: 'all', text: 'All media' },
		{ id: 'comics', text: 'Comics' },
		{ id: 'videos', text: 'Videos' },
		{ id: 'images', text: 'Images' }
	];
	let cancelling = $state<number | null>(null);
	// The running move or zip job: when it's gone, comic paths have changed.
	let comicJobId: number | null = null;
	// Folder comics that could become zips (null until looked up).
	let zipItems = $state<ComicZipPlanItem[] | null>(null);
	let findingZips = $state(false);
	let confirmZip = $state(false);
	let startingZip = $state(false);
	const zipReady = $derived(zipItems?.filter((i) => i.status === 'zip') ?? []);
	const zipConflicts = $derived(zipItems?.filter((i) => i.status === 'conflict') ?? []);

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

	async function loadCovers() {
		const { data, error } = await SystemService.coverRegenStatus();
		if (!error && data) covers = data;
		return covers?.running ?? false;
	}

	async function loadJobs() {
		const { data, error } = await SystemService.listJobs();
		if (!error && data) jobs = data;
		return !!jobs && (!!jobs.running || jobs.queued.length > 0);
	}

	// Poll faster while a job runs or waits, slow to a heartbeat when idle, so
	// the metrics stay live without hammering the backend.
	async function poll() {
		const [running, coversRunning, busy] = await Promise.all([
			loadScan(),
			loadCovers(),
			loadJobs()
		]);
		const current = jobs?.running;
		const comicJobDone = comicJobId !== null && current?.id !== comicJobId;
		if ((wasRunning && !running) || (coversWereRunning && !coversRunning) || comicJobDone) {
			// A scan may have imported or reconciled away media, a cover run
			// bumps every comic's cover version, and moves and zips change comic
			// paths; drop the cached lists so the next visit re-fetches them
			// (mediaStore).
			refreshMediaFiles();
		}
		comicJobId = current && ['move', 'zip'].includes(current.kind) ? current.id : null;
		wasRunning = running;
		coversWereRunning = coversRunning;
		timer = setTimeout(poll, running || coversRunning || busy ? 1000 : 5000);
	}

	// `missing` only fills in covers whose file doesn't exist; `all` rewrites
	// every cover (behind a confirm, since it reopens every archive).
	async function regenerateCovers(mode: 'all' | 'missing') {
		confirmCovers = false;
		startingCovers = true;
		const { data, error } = await SystemService.regenerateCovers({ query: { mode } });
		startingCovers = false;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to queue cover regeneration' }));
			return;
		}
		addNotification(new SuccessNotification({ subtitle: data.message }));
		clearTimeout(timer);
		poll();
	}

	async function findFolderComics() {
		findingZips = true;
		const { data, error } = await ComicsService.comicZipPreview();
		findingZips = false;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: "Couldn't look up folder comics" }));
			return;
		}
		zipItems = data.items;
	}

	async function convertToZip() {
		confirmZip = false;
		startingZip = true;
		const { data, error } = await ComicsService.comicZipConvert({
			body: { ids: zipReady.map((i) => i.id) }
		});
		startingZip = false;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to queue the conversion' }));
			return;
		}
		addNotification(new SuccessNotification({ subtitle: data.message }));
		// Look again once it has run; the list is stale from now on.
		zipItems = null;
		clearTimeout(timer);
		poll();
	}

	async function triggerScan() {
		triggering = true;
		const { data, error } = await SystemService.triggerScan({ query: { media_type: scanScope } });
		triggering = false;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to queue scan' }));
			return;
		}
		addNotification(new SuccessNotification({ subtitle: data.message }));
		clearTimeout(timer);
		poll();
		loadTasks();
	}

	async function cancelJob(job: JobInfo) {
		cancelling = job.id;
		const { data, error } = await SystemService.cancelJob({ path: { id: job.id } });
		cancelling = null;
		if (error || !data) {
			addNotification(new ErrorNotification({ subtitle: `Couldn't cancel ${jobLabel(job)}` }));
		} else {
			addNotification(
				new SuccessNotification({
					subtitle:
						data.status === 'cancelling'
							? `Stopping ${jobLabel(job)}…`
							: `Cancelled ${jobLabel(job)}`
				})
			);
		}
		clearTimeout(timer);
		poll();
	}

	function jobLabel(job: JobInfo): string {
		if (job.kind === 'scan') return `Scan (${job.params.media_type ?? 'all'})`;
		if (job.kind === 'move') {
			const folder = (job.params.target ?? '').split(/[/\\]/).pop();
			return `Move ${job.params.count ?? ''} comic(s) → ${folder}`;
		}
		if (job.kind === 'zip') return `Zip ${job.params.count ?? ''} folder comic(s)`;
		return job.params.mode === 'missing' ? 'Covers (missing only)' : 'Covers (all)';
	}

	function jobDuration(job: JobInfo): number | null {
		if (!job.started_at) return null;
		const end = job.finished_at ? Date.parse(job.finished_at) : Date.now();
		return (end - Date.parse(job.started_at)) / 1000;
	}

	function historyDetail(job: JobInfo): string {
		const took = jobDuration(job);
		return took === null
			? fmtTime(job.finished_at)
			: `${fmtTime(job.finished_at)} · took ${fmtDuration(took)}`;
	}

	const stateTag: Record<JobInfo['state'], 'blue' | 'gray' | 'green' | 'red' | 'warm-gray'> = {
		running: 'blue',
		queued: 'gray',
		succeeded: 'green',
		failed: 'red',
		cancelled: 'warm-gray'
	};

	onMount(() => {
		poll();
		loadTasks();
	});

	onDestroy(() => clearTimeout(timer));

	let lastStatus = $derived(scan?.last_result?.status as string | undefined);
	// Per-phase outcome of the last scan: [["images", "error"], ["comics", "done"], ...].
	let lastPhases = $derived(
		Object.entries((scan?.last_result?.phases ?? {}) as Record<string, string>)
	);
	const issueTag = { skipped: 'red', warning: 'warm-gray', error: 'red' } as const;
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
			<h3>Jobs</h3>
			{#if jobs?.running}
				<Tag type="blue">Busy</Tag>
			{:else}
				<Tag type="gray">Idle</Tag>
			{/if}
		</div>
		<p class="muted note">
			Scans, cover runs, comic moves and zips share one queue and run one at a time. Waiting jobs
			can be cancelled; a running cover run or zip stops after the comic in hand, a running scan or
			move can't be stopped.
		</p>
		{#if jobs?.running}
			{@const job = jobs.running}
			<div class="job">
				<Tag type="blue" size="sm">Running</Tag>
				<span class="job-label">{jobLabel(job)}</span>
				{#if job.progress}<span class="muted">{job.progress}</span>{/if}
				<span class="muted">{fmtDuration(jobDuration(job))}</span>
				{#if job.cancellable}
					<Button
						kind="ghost"
						size="small"
						icon={Close}
						iconDescription="Stop"
						disabled={cancelling === job.id}
						on:click={() => cancelJob(job)}
					/>
				{/if}
			</div>
		{/if}
		{#each jobs?.queued ?? [] as job (job.id)}
			<div class="job">
				<Tag type="gray" size="sm">Queued</Tag>
				<span class="job-label">{jobLabel(job)}</span>
				<Button
					kind="ghost"
					size="small"
					icon={Close}
					iconDescription="Cancel"
					disabled={cancelling === job.id}
					on:click={() => cancelJob(job)}
				/>
			</div>
		{/each}
		{#if !jobs?.running && !jobs?.queued.length}
			<p class="muted note">Nothing running or waiting.</p>
		{/if}
		{#if jobs?.history.length}
			<h4>Recent</h4>
			<ul class="failures">
				{#each jobs.history as job (job.id)}
					<li>
						<span class="job">
							<Tag type={stateTag[job.state]} size="sm">{job.state}</Tag>
							<span class="job-label">{jobLabel(job)}</span>
						</span>
						<span class="muted">{historyDetail(job)}</span>
						{#if job.error}
							<!-- A replaced job isn't a failure; only failed jobs show red. -->
							<span class={job.state === 'failed' ? 'err' : 'muted'} title={job.error}
								>{job.error}</span
							>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</Tile>

	<Tile class="card">
		<div class="card-head">
			<h3>Media scan</h3>
			{#if scan?.running}
				<Tag type="blue">Running</Tag>
			{:else if lastStatus === 'error'}
				<Tag type="red">Last run failed</Tag>
			{:else if lastStatus === 'partial'}
				<Tag type="magenta">Last run partly failed</Tag>
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
				{#if lastPhases.length}
					<dt>Phases</dt>
					<dd class="phases">
						{#each lastPhases as [name, outcome] (name)}
							<Tag type={outcome === 'done' ? 'green' : 'red'} size="sm">{name}</Tag>
						{/each}
					</dd>
				{/if}
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
			<dt>Issues</dt>
			<dd class:err={!!scan?.issue_count}>{scan?.issue_count ?? 0}</dd>
		</dl>
		{#if scan?.issues?.length}
			<h4>Issues</h4>
			<p class="muted note">
				Skipped files weren't imported and are retried on every scan; warnings didn't stop anything;
				errors stopped a whole phase.
			</p>
			<ul class="failures">
				{#each scan.issues as issue, i (i)}
					<li>
						<span class="issue-head">
							<Tag type={issueTag[issue.level]} size="sm">{issue.level}</Tag>
							<Tag type="outline" size="sm">{issue.media}</Tag>
							{#if issue.path}<span class="issue-path" title={issue.path}>{issue.path}</span>{/if}
						</span>
						<span class={issue.level === 'warning' ? 'muted' : 'err'} title={issue.reason}
							>{issue.reason}</span
						>
					</li>
				{/each}
			</ul>
			{#if (scan.issue_count ?? 0) > scan.issues.length}
				<p class="muted">…and {(scan.issue_count ?? 0) - scan.issues.length} more</p>
			{/if}
		{/if}

		<div class="scan-actions">
			<Dropdown
				size="sm"
				titleText="Scan"
				hideLabel
				items={scanScopes}
				bind:selectedId={scanScope}
			/>
			<Button icon={Renew} disabled={triggering} on:click={triggerScan}>
				{scan?.running ? 'Queue another scan' : 'Scan now'}
			</Button>
		</div>
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
		<div class="card-head">
			<h3>Covers</h3>
			{#if covers?.running}
				<Tag type="blue">Running</Tag>
			{:else if covers?.cancelled}
				<Tag type="warm-gray">Cancelled</Tag>
			{:else if covers?.failed}
				<Tag type="red">{covers.failed} failed</Tag>
			{:else if covers?.finished_at}
				<Tag type="green">Done</Tag>
			{/if}
		</div>
		<p class="muted">
			Builds covers from each comic's chosen cover page (or the first page) and refreshes its page
			count. <em>Generate missing</em> only fills in comics without a cover; <em>Regenerate all</em>
			rewrites every one. Covers that can't be generated are removed instead of left stale.
		</p>
		{#if covers?.running}
			<ProgressBar
				value={covers.processed}
				max={covers.total || undefined}
				labelText={`Processed ${covers.processed} / ${covers.total}`}
			/>
		{:else if covers?.finished_at}
			<dl class="kv">
				<dt>Mode</dt>
				<dd>{covers.mode === 'missing' ? 'Missing only' : 'All'}</dd>
				<dt>Finished</dt>
				<dd>{fmtTime(covers.finished_at)}</dd>
				<dt>Generated</dt>
				<dd>{covers.processed - covers.failed} / {covers.total}</dd>
				<dt>Failed</dt>
				<dd>{covers.failed}</dd>
			</dl>
		{/if}
		{#if covers?.failures.length}
			<h4>Failed comics</h4>
			<ul class="failures">
				{#each covers.failures as f (f.id)}
					<li>
						<a href="/comic/{f.id}" title={f.name}>{f.name}</a>
						<span class="err" title={f.reason}>{f.reason}</span>
					</li>
				{/each}
			</ul>
			{#if covers.failed > covers.failures.length}
				<p class="muted">…and {covers.failed - covers.failures.length} more</p>
			{/if}
		{/if}
		<div class="buttons">
			<Button
				icon={ImageIcon}
				disabled={startingCovers}
				on:click={() => regenerateCovers('missing')}
			>
				Generate missing
			</Button>
			<Button kind="tertiary" disabled={startingCovers} on:click={() => (confirmCovers = true)}
				>Regenerate all</Button
			>
		</div>
	</Tile>

	<Tile class="card">
		<div class="card-head">
			<h3>Folder comics</h3>
			{#if zipItems}
				<Tag type={zipItems.length ? 'blue' : 'green'}>{zipItems.length} found</Tag>
			{/if}
		</div>
		<p class="muted">
			A comic kept as a folder of images is hundreds of files to scan, read and copy, which is slow
			on network drives. <em>Convert to zip</em> packs each folder into an uncompressed zip next to
			it (<code>Name</code> → <code>Name.zip</code>), checks every file reads back intact, then
			deletes the folder. The comic keeps its favorite, progress and cover. Stopping the job keeps
			the comics already converted.
		</p>
		{#if zipItems}
			<dl class="kv">
				<dt>To convert</dt>
				<dd>{zipReady.length} ({zipReady.reduce((n, i) => n + i.pages, 0)} pages)</dd>
				<dt>Name taken</dt>
				<dd>{zipConflicts.length}</dd>
			</dl>
			{#if zipConflicts.length}
				<h4>Skipped</h4>
				<ul class="failures">
					{#each zipConflicts as item (item.id)}
						<li>
							<a href="/comic/{item.id}" title={item.source}>{item.name}</a>
							<span class="err" title={item.reason}>{item.reason}</span>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
		<div class="buttons">
			<Button
				kind={zipItems ? 'tertiary' : 'primary'}
				icon={Search}
				disabled={findingZips}
				on:click={findFolderComics}
			>
				{findingZips ? 'Looking…' : zipItems ? 'Look again' : 'Find folder comics'}
			</Button>
			{#if zipItems}
				<Button
					icon={Archive}
					disabled={!zipReady.length || startingZip}
					on:click={() => (confirmZip = true)}
				>
					Convert {zipReady.length} to zip
				</Button>
			{/if}
		</div>
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

<Modal
	bind:open={confirmCovers}
	modalHeading="Regenerate all covers?"
	primaryButtonText="Regenerate"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmCovers = false)}
	on:submit={() => regenerateCovers('all')}
>
	<p>
		Every comic's cover is rebuilt from its archive, which can take a while on a large library.
		Custom cover pages are kept.
	</p>
</Modal>

<Modal
	bind:open={confirmZip}
	modalHeading="Convert {zipReady.length} folder comic(s) to zip?"
	primaryButtonText="Convert"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmZip = false)}
	on:submit={convertToZip}
>
	<p>
		Each folder is replaced by a zip of the same name holding its files unchanged; a folder is
		deleted only after its zip checks out. The drive needs room for one more copy of the comic being
		converted. This reads and writes every page, so a large library takes a while.
	</p>
</Modal>

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

	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.scan-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.5rem;
	}

	.scan-actions :global(.bx--dropdown__wrapper) {
		min-width: 9rem;
	}

	.phases {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.issue-head {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
	}

	.issue-path {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.job {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
		font-size: 0.875rem;
	}

	.job-label {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.note {
		margin: 0;
		font-size: 0.8125rem;
	}

	.failures {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.8125rem;
	}

	.failures li {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.failures a,
	.failures span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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
