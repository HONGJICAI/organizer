<script lang="ts">
	import {
		Accordion,
		AccordionItem,
		Button,
		SkeletonPlaceholder,
		Tag
	} from 'carbon-components-svelte';
	import { onMount } from 'svelte';
	import TagLink from './TagLink.svelte';

	interface Props {
		tag2countMap?: Map<string, number>;
		onClickTag?: (tag: string) => void;
		/** Set to make tags links (same tab, middle-click opens a new one) instead of calling onClickTag. */
		tagHref?: (tag: string) => string;
		title: string;
		skeleton?: boolean;
		defaultOpen?: boolean;
	}

	let {
		tag2countMap,
		onClickTag,
		tagHref,
		title = 'Tags',
		skeleton,
		defaultOpen = true
	}: Props = $props();
	let open = $state(defaultOpen);
	const showMoreNumber = 20;
	let currentShowNumber = $state(20);
	let orderedTag2countMap = $derived(
		new Map(
			[...(tag2countMap?.entries() ?? [])].sort((a, b) => b[1] - a[1]).slice(0, currentShowNumber)
		)
	);

	onMount(() => {
		// if mobile
		if (window.innerWidth < 640) {
			open = false;
		}
	});
</script>

<Accordion size="sm">
	<AccordionItem bind:open {title}>
		{#if skeleton}
			<SkeletonPlaceholder style="width: 100%; height: 80vh" />
		{/if}
		{#each orderedTag2countMap as [tag, count]}
			{#snippet label()}
				<div class="tag">
					<span class="truncated" title={tag}>{tag}</span>
					<span class="fixed">:{count}</span>
				</div>
			{/snippet}
			{#if tagHref}
				<TagLink href={tagHref(tag)}>{@render label()}</TagLink>
			{:else}
				<Tag on:click={() => onClickTag?.(tag)} interactive={true}>{@render label()}</Tag>
			{/if}
		{/each}

		{#if currentShowNumber < (tag2countMap?.size ?? 0)}
			<Button kind="ghost" size="small" on:click={() => (currentShowNumber += showMoreNumber)}
				>Show more...</Button
			>
		{/if}
	</AccordionItem>
</Accordion>

<style>
	.tag {
		display: flex;
	}

	.truncated {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.fixed {
		flex-shrink: 0;
	}
</style>
