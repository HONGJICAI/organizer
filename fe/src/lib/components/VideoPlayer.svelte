<script lang="ts">
	import { ProgressBar } from 'carbon-components-svelte';
	import { config, ViewMode } from '$lib/config.svelte';
	import { viewModeClass } from '$lib/reader';
	import type { Video } from '$lib/model.svelte';

	interface Props {
		file: Video;
	}
	let { file }: Props = $props();

	let videoTarget: HTMLVideoElement | null = $state(null);
	let videoTime = $state(0);
	let duration = $state(9999999);

	const src = $derived(`${config.apiServer}/videos/${file.id}`);
	const viewClass = $derived(viewModeClass(config.viewMode as ViewMode));
</script>

<div class="viewer-root">
	<div class={viewClass}>
		<ProgressBar hideLabel max={duration} value={videoTime} />
		<video
			bind:this={videoTarget}
			{src}
			controls
			autoplay
			loop
			ontimeupdate={() => {
				if (videoTarget) {
					videoTime = videoTarget.currentTime;
					duration = videoTarget.duration;
				}
			}}
		>
			<track kind="captions" />
		</video>
	</div>
</div>

<style>
	.viewer-root {
		user-select: none;
	}

	.fit-to-height {
		overflow-x: hidden;
	}
	.fit-to-height video {
		height: calc(100vh - 6rem);
	}

	.fit-to-width {
		max-width: 100vw;
	}
	.fit-to-width video {
		width: 100vw;
	}

	.fit-to-contain video {
		max-height: calc(100vh - 6rem);
		max-width: 100vw;
		width: auto;
		height: auto;
	}

	video {
		display: block;
		margin-left: auto;
		margin-right: auto;
		-webkit-user-drag: none;
	}
</style>
