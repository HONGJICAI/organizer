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
	import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
	import { config } from '$lib/config';
	import { Close } from 'carbon-icons-svelte';
	import { onMount } from 'svelte';
	interface Props {
		file: MediaFile;
		onClose: () => void;
	}

	let { file, onClose }: Props = $props();
	let comicTarget: null | HTMLImageElement = $state(null);
	let targets: ReadonlyArray<null | HTMLElement> = $derived([comicTarget]);
	let videoTarget: null | HTMLVideoElement = $state(null);
	let maxPage = $state(0);
	let loading = $state(true);
	let page = $state(1);
	let objUrl = $state('');
	let nextUrl = $state('');
	let videoTime = $state(0);
	let duration = $state(9999999);

	let comic = $derived(file as Comic);
	let video = $derived(file as Video);

	$effect(() => {
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
	});

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
		const ct = e.currentTarget as HTMLElement;
		if (!ct) {
			return;
		}
		const imgLeft = ct.getBoundingClientRect().left;
		const imgRight = ct.getBoundingClientRect().right;

		if (e.x < imgLeft + (imgRight - imgLeft) / 2) {
			goPrevPage();
		} else {
			goNextPage();
		}
	}

	async function onLikePage(e: CustomEvent<null>) {
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

	async function onSetCover(e: CustomEvent<null>) {
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
	{#if file.type === MediaType.Comic}
		<ProgressBar hideLabel max={maxPage} value={page} />
		<div onclick={onClickImage} role="none">
			<img
				bind:this={comicTarget}
				src={objUrl}
				alt="comic content"
				onload={() => {
					loading = false;
					preloadImageAsync(nextUrl);
				}}
			/>
		</div>
	{/if}
	{#if file.type === MediaType.Video}
		<ProgressBar hideLabel max={duration} value={videoTime} />
		<video
			bind:this={videoTarget}
			src={objUrl}
			controls
			autoplay
			loop
			oncanplay={() => {
				loading = false;
			}}
			ontimeupdate={(e) => {
				if (videoTarget) {
					videoTime = videoTarget.currentTime;
					duration = videoTarget.duration;
				}
			}}
		>
			<track kind="captions" />
		</video>
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

<ContextMenu target={targets}>
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
