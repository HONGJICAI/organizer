<script lang="ts">
	import {
		Button,
		ContextMenu,
		ContextMenuDivider,
		ContextMenuGroup,
		ContextMenuOption,
		InlineLoading,
		PaginationNav,
		ProgressBar
	} from 'carbon-components-svelte';
	import { Comic, MediaFile, MediaType, Video } from '$lib/model';
	import { config } from '$lib/config';
	import { Close } from 'carbon-icons-svelte';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	export let file: MediaFile;
	export let onClose: () => void;
	let target: null | ReadonlyArray<null | HTMLElement>;
	let maxPage = 0;
	let loading = true;
	let page = 1;
	let objUrl = '';
	let nextUrl = '';
	let videoTime = 0;
	let duration = 9999999;

	$: comic = file.type === MediaType.Comic ? (file as Comic) : null;
	$: video = file.type === MediaType.Video ? (file as Video) : null;

	$: {
		switch (file.type) {
			case MediaType.Comic:
				maxPage = comic.page ?? 0;
				// allPageUrls = Array.from(
				// 	{ length: maxPage },
				// 	(_, i) => `${config.apiServer}/api/comics/${comic?.id}/${i + 1}`
				// );
				objUrl = `${config.apiServer}/api/comics/${comic?.id}/${page}`;
				nextUrl =
					page + 1 <= maxPage ? `${config.apiServer}/api/comics/${comic?.id}/${page + 1}` : '';
				break;
			case MediaType.Video:
				objUrl = `${config.apiServer}/videos/${video?.id}`;
				break;
		}
	}

	onMount(() => {
		//scroll to top
		window.scrollTo(0, 0);
		window.addEventListener('keydown', handleKeydown);
		return () => {
			window.removeEventListener('keydown', handleKeydown);
		};
	});

	const onCloseModal = () => {
		onClose();
	};

	const preloadImageAsync = async (url: string) => {
		new Promise((resolve, reject) => {
			const img = new Image();
			img.onload = resolve;
			img.onerror = reject;
			img.src = url;
		});
	};

	const handleKeydown = (event: KeyboardEvent) => {
		if (event.key === 'ArrowLeft') {
			page = (page - 1 + maxPage) % maxPage;
		} else if (event.key === 'ArrowRight') {
			page = (page + 1) % maxPage;
		}
	};

	const goNextPage = () => {
		if (loading) {
			return;
		}
		loading = true;
		page = page + 1;
		if (page > maxPage) {
			page = maxPage;
			loading = false;
		}
	};

	const goPrevPage = () => {
		if (loading) {
			return;
		}
		loading = true;
		page = page - 1;
		if (page < 1) {
			page = 1;
			loading = false;
		}
	};

	function onClickImage(e: MouseEvent): void {
		const imgLeft = e.currentTarget!.getBoundingClientRect().left;
		const imgRight = e.currentTarget!.getBoundingClientRect().right;

		if (e.x < imgLeft + (imgRight - imgLeft) / 2) {
			goPrevPage();
		} else {
			goNextPage();
		}
	}

	async function onLikePage(e: MouseEvent) {
		if (!comic) {
			return;
		}
		const rsp = await fetch(`${config.apiServer}/api/comics/${comic.id}/${page}/like`, {
			method: 'POST'
		});
		if (rsp.ok) {
		} else {
			alert(rsp.status);
		}
	}

	async function onSetCover(e: MouseEvent) {
		if (!comic) {
			return;
		}
		const rsp = await fetch(`${config.apiServer}/api/comics/${comic.id}/${page}/cover`, {
			method: 'POST'
		});
		if (rsp.ok) {
		} else {
			alert(rsp.status);
		}
	}
</script>

<div style="position:fixed;top:0;left:30%;z-index:9999;">
	<div style="display: flex;">
		<Button on:click={onCloseModal} icon={Close} iconDescription="Close" />
		{#if loading}
			<InlineLoading />
		{/if}
	</div>
</div>
<container>
	{#if comic}
		<ProgressBar hideLabel max={maxPage} value={page} />
		<div on:click={onClickImage} role="button">
			<img
				bind:this={target}
				src={objUrl}
				alt="comic content"
				on:load={() => {
					loading = false;
					preloadImageAsync(nextUrl);
				}}
			/>
		</div>
	{/if}
	{#if video}
		<ProgressBar hideLabel max={duration} value={videoTime} />
		<video
			bind:this={target}
			src={objUrl}
			controls
			autoplay
			loop
			on:canplay={() => {
				loading = false;
			}}
			on:timeupdate={(e) => {
				videoTime = e.target.currentTime;
				duration = e.target.duration;
			}}
		/>
	{/if}

	<!-- {#each allPageUrls as url}		
		<img src={url} loading="lazy" alt="comic content" style="max-width:100%" />
	{/each} -->
</container>
{#if comic}
	<div id="pagination">
		<PaginationNav bind:page total={maxPage} loop={true} shown={5} />
	</div>
{/if}

<ContextMenu {target}>
	<ContextMenuOption indented labelText="Like page" on:click={onLikePage} />
	<ContextMenuOption indented labelText="Set as Cover" on:click={onSetCover} />
	<ContextMenuDivider />
	<ContextMenuOption indented labelText="Export as">
		<ContextMenuGroup labelText="Export options">
			<ContextMenuOption id="pdf" labelText="PDF" />
		</ContextMenuGroup>
	</ContextMenuOption>
	<ContextMenuDivider />
	<ContextMenuOption selectable labelText="Remove metadata" />
	<ContextMenuDivider />
	<ContextMenuGroup labelText="Style options">
		<ContextMenuOption id="0" labelText="Font smoothing" selected />
		<ContextMenuOption id="1" labelText="Reduce noise" />
	</ContextMenuGroup>
	<ContextMenuDivider />
	<ContextMenuOption indented kind="danger" labelText="Delete" />
</ContextMenu>

<style>
	container {
		max-height: 90vh;
		max-width: 100vw;
		height: 90vh;
		width: 100vw;
	}

	img,
	video {
		display: block;
		margin-left: auto;
		margin-right: auto;
		max-height: 90vh;
		max-width: 100vw;
	}
</style>
