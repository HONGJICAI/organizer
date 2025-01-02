<script lang="ts">
	import { Accordion, AccordionItem, Button, Tag, Truncate } from 'carbon-components-svelte';
	import { onMount } from 'svelte';

	interface Props {
		tag2countMap: Map<string, number>;
		onClickTag: (tag: string) => void;
		title: string;
	}

	let { tag2countMap, onClickTag, title = 'Tags' }: Props = $props();
	let open = $state(true);
	const showMoreNumber = 20;
	let currentShowNumber = $state(20);
	let orderedTag2countMap = $derived(new Map(
		[...tag2countMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, currentShowNumber)
	));

	onMount(() => {
		// if mobile
		if (window.innerWidth < 640) {
			open = false;
		}
	});
</script>

<Accordion size="sm">
	<AccordionItem bind:open title={title}>
		{#each orderedTag2countMap as [tag, count], i}
			<Tag on:click={() => onClickTag(tag)} interactive={true}>
				<Truncate>{tag}:{count}</Truncate>
			</Tag>
		{/each}

		{#if currentShowNumber < tag2countMap.size}
			<Button size="small" on:click={() => (currentShowNumber += showMoreNumber)}
				>Show more...</Button
			>
		{/if}
	</AccordionItem>
</Accordion>
