<script lang="ts">
	import { Accordion, AccordionItem, Button, SkeletonPlaceholder, Tag, Truncate } from 'carbon-components-svelte';
	import { onMount } from 'svelte';

	interface Props {
		tag2countMap?: Map<string, number>;
		onClickTag?: (tag: string) => void;
		title: string;
		skeleton?: boolean;
	}

	let { tag2countMap, onClickTag, title = 'Tags', skeleton }: Props = $props();
	let open = $state(true);
	const showMoreNumber = 20;
	let currentShowNumber = $state(20);
	let orderedTag2countMap = $derived(
		new Map([...tag2countMap?.entries() ?? []].sort((a, b) => b[1] - a[1]).slice(0, currentShowNumber))
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
		{#each orderedTag2countMap as [tag, count], i}
			<Tag on:click={() => onClickTag?.(tag)} interactive={true}>
				<Truncate>{tag}:{count}</Truncate>
			</Tag>
		{/each}

		{#if currentShowNumber < (tag2countMap?.size ?? 0)}
			<Button size="small" on:click={() => (currentShowNumber += showMoreNumber)}
				>Show more...</Button
			>
		{/if}
	</AccordionItem>
</Accordion>
