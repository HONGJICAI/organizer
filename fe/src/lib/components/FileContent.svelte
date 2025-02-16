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
	import {
		Comic,
		ErrorNotification,
		MediaFile,
		MediaType,
		SuccessNotification,
		Video
	} from '$lib/model.svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { Close } from 'carbon-icons-svelte';
	import { onMount } from 'svelte';
	import { addNotification } from '$lib/state.svelte';
	import { ComicpageService } from '$lib/client';
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
	const comicViewMode = $derived.by(() => {
		switch (config.viewMode) {
			case ViewMode.Height:
				return 'fit-to-height';
			case ViewMode.Width:
				return 'fit-to-width';
		}
	});

	let comic = $derived(file as Comic);
	let video = $derived(file as Video);

	$effect(() => {
		switch (file.type) {
			case MediaType.Comic:
				maxPage = comic.page ?? 0;
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
		//scroll to top
		window.scrollTo(0, 0);
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
		//scroll to top
		window.scrollTo(0, 0);
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
		const { data, error } = await ComicpageService.comicPageLike({
			path: {
				id: comic.id,
				page: page
			}
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to like page' }));
		} else {
			addNotification(new SuccessNotification({ subtitle: 'Successfully liked page' }));
		}
	}

	async function onSetCover(e: CustomEvent<null>) {
		if (!comic) {
			return;
		}
		const { data, error } = await ComicpageService.comicPageSetCover({
			path: {
				id: comic.id,
				page: page
			}
		});
		if (error) {
			addNotification(new ErrorNotification({ subtitle: 'Failed to set as cover' }));
		} else {
			fetch(comic.coverUrl, { cache: 'reload', mode: 'no-cors' });
			var cover = document.getElementById(comic.coverId) as HTMLImageElement;
			if (cover) {
				cover.src = comic.coverUrl;
			}
			addNotification(new SuccessNotification({ subtitle: 'Successfully set as cover' }));
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
<container class={comicViewMode}>
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
				onerror={() => {
					loading = false;
					addNotification(new ErrorNotification({ subtitle: 'Failed to load comic page' }));
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
	<ContextMenuOption indented kind="danger" labelText="Delete" />
</ContextMenu>

<style>
	.fit-to-height {
		height: 90vh;
	}
	.fit-to-height img,
	video {
		height: 90vh;
	}

	.fit-to-width {
		max-width: 100vw;
	}
	.fit-to-width img,
	video {
		width: 100vw;
	}

	img,
	video {
		display: block;
		margin-left: auto;
		margin-right: auto;
	}
</style>
