<script lang="ts">
	import FileCard from '$lib/components/FileCard.svelte';
	import HorizontalScroller from '$lib/components/HorizontalScroller.svelte';
	import { HomeService } from '$lib/client/sdk.gen.js';
	import { homeRows, randomRow, readerUrl, type HomeRows } from '$lib/home';
	import { errorMessage } from '$lib/mediaAdapters';
	import { Button, InlineNotification, SkeletonPlaceholder } from 'carbon-components-svelte';
	import { Book, Image as ImageIcon, MediaLibrary, Renew } from 'carbon-icons-svelte';

	let { data } = $props();

	let rows = $state<HomeRows | null>(null);
	let error = $state('');
	let shuffling = $state(false);

	$effect(() => {
		const request = data.home;
		rows = null;
		error = '';
		request.then(({ data: home, error: e }) => {
			if (request !== data.home) return;
			if (home) rows = homeRows(home);
			else error = errorMessage(e);
		});
	});

	async function shuffle() {
		shuffling = true;
		const { data: home } = await HomeService.homeGet();
		if (home && rows) rows.random = randomRow(home.random);
		shuffling = false;
	}

	const sections = $derived(
		rows
			? [
					{ key: 'continue', title: 'Continue reading', files: rows.continueReading, resume: true },
					{ key: 'recent', title: 'Recently added', files: rows.recent, resume: false },
					{ key: 'favorites', title: 'Favorites', files: rows.favorites, resume: false },
					{ key: 'random', title: 'Random picks', files: rows.random, resume: false }
				].filter((s) => s.files.length > 0)
			: []
	);
</script>

<div class="home">
	<nav class="types" aria-label="Libraries">
		<a href="/comic"><Book size={20} /><span>Comics</span></a>
		<a href="/video"><MediaLibrary size={20} /><span>Videos</span></a>
		<a href="/image"><ImageIcon size={20} /><span>Images</span></a>
	</nav>

	{#if error}
		<InlineNotification kind="error" title="Couldn't load the home page" subtitle={error} />
	{:else if !rows}
		<section>
			<SkeletonPlaceholder style="width: 10rem; height: 1.5rem;" />
			<HorizontalScroller>
				{#each { length: 8 } as _}
					<div class="card-skeleton">
						<SkeletonPlaceholder style="width: 100%; height: 100%;" />
					</div>
				{/each}
			</HorizontalScroller>
		</section>
	{:else if sections.length === 0}
		<div class="empty">
			<p>Nothing here yet</p>
			<p class="hint">Run a media scan from <a href="/admin">Admin</a> to fill your library.</p>
		</div>
	{:else}
		{#each sections as section (section.key)}
			<section>
				<div class="heading">
					<h2>{section.title}</h2>
					{#if section.key === 'random'}
						<Button kind="ghost" size="small" icon={Renew} disabled={shuffling} on:click={shuffle}
							>Shuffle</Button
						>
					{/if}
				</div>
				<HorizontalScroller>
					{#each section.files as file (`${file.type}-${file.id}`)}
						<FileCard
							{file}
							showType
							showProgress={section.resume}
							href={readerUrl(file, section.resume)}
						/>
					{/each}
				</HorizontalScroller>
			</section>
		{/each}
	{/if}
</div>

<style>
	.home {
		/* Smaller cards than the list pages, so a row shows more at a glance. */
		--card-width: 200px;
		--card-height: calc(var(--card-width) * 1.5);
		padding: 1rem 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.75rem;
	}

	@media (max-width: 768px) {
		.home {
			/* Two and a bit cards per screen: the cut-off one says "swipe". */
			--card-width: 40vw;
			padding: 0.75rem;
			gap: 1.25rem;
		}
		h2 {
			font-size: 1rem;
		}
	}

	section {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		min-width: 0;
	}

	.types {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.types a {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background: var(--cds-ui-01, #262626);
		color: var(--cds-text-01, #f4f4f4);
		text-decoration: none;
		font-size: 0.875rem;
	}

	.types a:hover {
		background: var(--cds-hover-ui, #333333);
	}

	@media (max-width: 768px) {
		.types a {
			flex: 1;
			justify-content: center;
			padding: 0.5rem;
		}
	}

	.heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		min-height: 2rem;
	}

	h2 {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--cds-text-01, #f4f4f4);
	}

	.card-skeleton {
		width: var(--card-width);
		height: var(--card-height);
		flex-shrink: 0;
	}

	.empty {
		padding: 3rem 1rem;
		text-align: center;
		color: var(--cds-text-01, #f4f4f4);
	}

	.empty .hint {
		margin-top: 0.5rem;
		color: var(--cds-text-02, #c6c6c6);
	}
</style>
