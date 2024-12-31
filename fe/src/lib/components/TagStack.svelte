<script lang="ts">
	import { Accordion, AccordionItem, Button, Tag, Truncate } from 'carbon-components-svelte';
	import { onMount } from 'svelte';

	export let tag2countMap: Map<string, number>;
	export let onClickTag: (tag: string) => void;
	export let title = 'Tags';
	let open = true;
	const showMoreNumber = 20;
	let currentShowNumber = 20;
	$: orderedTag2countMap = new Map(
		[...tag2countMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, currentShowNumber)
	);

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
