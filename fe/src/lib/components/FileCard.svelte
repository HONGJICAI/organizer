<script lang="ts">
	import { Tile } from 'carbon-components-svelte';
	import { Comic, MediaFile, MediaType } from '$lib/model.svelte';
    interface Props {
        file: MediaFile;
        light?: boolean;
        onClickFile: (file: MediaFile) => void;
    }

    let { file, light = $bindable(false), onClickFile }: Props = $props();
    let comic = $derived(file as Comic);
</script>

<div class="card">
	<Tile bind:light on:click={() => onClickFile(file)}>
		<img
			src={file.coverUrl}
			alt={`${file.id}`}
			style="width:100%;height:100%;object-fit:cover;max-height:50vh;"
		/>
        <div class="left-top"> {file.size}MB </div>
        {#if file.type === MediaType.Comic}
            <div class="top-right"> {comic.page}p
            </div>
        {/if}
		{file.name}
	</Tile>
</div>

<style>
	.card {
		width: 300px;
        position: relative;
	}

    .card:hover {
        cursor: pointer;
    }

    .top-right {
        position: absolute;
        top: 0;
        right: 0;
    }

    .left-top {
        position: absolute;
        top: 0;
        left: 0;
    }
</style>
