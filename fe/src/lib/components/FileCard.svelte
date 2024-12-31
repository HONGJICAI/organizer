<script lang="ts">
	import { Tile } from 'carbon-components-svelte';
	import { MediaFile, MediaType } from '$lib/model';
	import { config } from '$lib/config';
	export let file: MediaFile;
	export let light = false;
	export let onClickFile: (file: MediaFile) => void;
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
            <div class="top-right"> {file.page}p
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
