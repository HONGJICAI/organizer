<script lang="ts">
	import { ComicsService, SystemService } from '$lib/client';
	import type { MediaFile } from '$lib/model.svelte';
	import { errorMessage } from '$lib/mediaAdapters';
	import { planAuthors } from '$lib/authorPlan';
	import { tagState } from '$lib/tags.svelte';
	import {
		Button,
		InlineLoading,
		InlineNotification,
		Link,
		Modal,
		StructuredList,
		StructuredListBody,
		StructuredListCell,
		StructuredListHead,
		StructuredListRow
	} from 'carbon-components-svelte';
	import { FolderMoveTo } from 'carbon-icons-svelte';
	import { onDestroy } from 'svelte';

	// Every author tag (Tags -> Classify) with how many of its comics aren't in
	// a folder named after it yet, and one button to gather them all: one move
	// job per author, into the folder the backend suggests.

	interface Props {
		files: MediaFile[];
		mediaType: string;
		/** Called after the moves finished, to reload the list. */
		onDone: () => void;
	}
	let { files, mediaType, onDone }: Props = $props();

	const plans = $derived(planAuthors(files, tagState.index));
	const todo = $derived(plans.authors.filter((a) => a.outside.length > 0));
	const todoCount = $derived(todo.reduce((n, a) => n + a.outside.length, 0));

	let confirmOpen = $state(false);
	let running = $state(false);
	let progress = $state('');
	let showMulti = $state(false);
	let result = $state<{ moved: number; failed: string[] } | null>(null);
	let timer: ReturnType<typeof setTimeout> | undefined;
	onDestroy(() => clearTimeout(timer));

	async function gatherAll() {
		confirmOpen = false;
		running = true;
		result = null;
		const jobs: { id: number; author: string }[] = [];
		const failed: string[] = [];
		for (const [i, plan] of todo.entries()) {
			progress = `Queueing ${i + 1} of ${todo.length}: ${plan.author}`;
			// All of the author's comics, so an existing folder of theirs is found.
			const suggested = await ComicsService.comicMoveSuggest({
				body: { ids: plan.ids, name: plan.author }
			});
			const target = suggested.data?.target;
			if (!target) {
				failed.push(`${plan.author}: no folder name could be made from it`);
				continue;
			}
			const { data, error } = await ComicsService.comicMove({
				body: { ids: plan.outside, target }
			});
			if (data) jobs.push({ id: data.jobId, author: plan.author });
			else failed.push(`${plan.author}: ${errorMessage(error)}`);
		}
		progress = `Moving… (${jobs.length} job(s), see Admin → Jobs)`;
		await waitFor(jobs, failed);
		running = false;
		onDone();
	}

	// Done once none of the jobs is queued or running. The history only keeps
	// the last 20 jobs, so a job that dropped out of it counts as finished.
	function waitFor(jobs: { id: number; author: string }[], failed: string[]) {
		return new Promise<void>((resolve) => {
			const poll = async () => {
				const { data } = await SystemService.listJobs();
				const active = new Set(
					[data?.running, ...(data?.queued ?? [])].flatMap((j) => (j ? [j.id] : []))
				);
				if (!data || jobs.some((j) => active.has(j.id))) {
					timer = setTimeout(poll, 1500);
					return;
				}
				let moved = 0;
				for (const job of jobs) {
					const done = data.history.find((h) => h.id === job.id);
					if (done && done.state !== 'succeeded') {
						failed.push(`${job.author}: ${done.error ?? done.state}`);
					} else {
						moved++;
					}
				}
				result = { moved, failed };
				resolve();
			};
			poll();
		});
	}
</script>

{#if plans.authors.length === 0}
	<p class="muted">
		No author tags yet. Mark tags as authors under <Link href="/{mediaType}/tag?view=classify"
			>Tags → Classify</Link
		>, or enter a tag above to gather its comics.
	</p>
{:else}
	<h4>Authors</h4>
	<p class="muted">
		{plans.authors.length} author(s); {todoCount} comic(s) aren't in a folder named after their author
		yet.
		{#if plans.multi.length}
			{plans.multi.length} comic(s) with several authors are left out
			<button class="link-button" onclick={() => (showMulti = !showMulti)}
				>{showMulti ? 'hide' : 'show'}</button
			>.
		{/if}
	</p>
	{#if showMulti}
		<ul class="multi">
			{#each plans.multi as m (m.id)}
				<li>
					{m.name} —
					{#each m.authors as a, i (a)}{i ? ', ' : ''}<Link href="?tag={encodeURIComponent(a)}"
							>{a}</Link
						>{/each}
				</li>
			{/each}
		</ul>
	{/if}

	<div class="controls">
		<Button
			icon={FolderMoveTo}
			disabled={!todoCount || running}
			on:click={() => (confirmOpen = true)}
			>Gather all ({todoCount} comic{todoCount === 1 ? '' : 's'})</Button
		>
		{#if running}<InlineLoading description={progress} />{/if}
	</div>
	{#if result}
		<InlineNotification
			kind={result.failed.length ? 'warning' : 'success'}
			title={result.failed.length ? 'Gathered with problems' : 'Gathered'}
			subtitle={`${result.moved} author(s) moved.${result.failed.length ? ' ' + result.failed.join('; ') : ''}`}
			on:close={() => (result = null)}
		/>
	{/if}

	<StructuredList condensed>
		<StructuredListHead>
			<StructuredListRow head>
				<StructuredListCell head>Author</StructuredListCell>
				<StructuredListCell head>Comics</StructuredListCell>
				<StructuredListCell head>Outside its folder</StructuredListCell>
				<StructuredListCell head></StructuredListCell>
			</StructuredListRow>
		</StructuredListHead>
		<StructuredListBody>
			{#each plans.authors as a (a.author)}
				<StructuredListRow>
					<StructuredListCell><span class="author">{a.author}</span></StructuredListCell>
					<StructuredListCell>{a.ids.length}</StructuredListCell>
					<StructuredListCell>{a.outside.length || '—'}</StructuredListCell>
					<StructuredListCell>
						<Link href="?tag={encodeURIComponent(a.author)}">Review…</Link>
					</StructuredListCell>
				</StructuredListRow>
			{/each}
		</StructuredListBody>
	</StructuredList>
{/if}

<Modal
	bind:open={confirmOpen}
	modalHeading="Gather {todoCount} comic(s) of {todo.length} author(s)?"
	primaryButtonText="Gather"
	secondaryButtonText="Cancel"
	on:click:button--secondary={() => (confirmOpen = false)}
	on:submit={gatherAll}
>
	<p>
		Each author's comics move into their suggested folder: one they already have, else one in the
		artist folder. Every author is its own background job; comics that conflict are skipped. Use
		<em>Review…</em> to check one author first.
	</p>
</Modal>

<style>
	.muted {
		color: var(--cds-text-02, #c6c6c6);
		font-size: 0.875rem;
		margin: 0.5rem 0;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
		margin: 1rem 0;
	}
	.multi {
		margin: 0.5rem 0 1rem 1rem;
		font-size: 0.8125rem;
		list-style: disc;
		overflow-wrap: anywhere;
	}
	.author {
		overflow-wrap: anywhere;
	}
	.link-button {
		background: none;
		border: none;
		padding: 0;
		color: var(--cds-link-01, #78a9ff);
		font: inherit;
		cursor: pointer;
	}
</style>
