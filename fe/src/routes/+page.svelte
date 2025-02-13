<script lang="ts">
	import { Accordion, AccordionItem, Link, SkeletonPlaceholder } from 'carbon-components-svelte';

	let { data } = $props();
</script>

<Accordion>
	{#await data.placeholder}
		<SkeletonPlaceholder style="width: 100%"/>
	{:then data}
		<AccordionItem open title="Comics">
            <Link href="/comic">All</Link>
			<p>Comics</p>
		</AccordionItem>
		<AccordionItem open title="Videos">
            <Link href="/video">All</Link>
			<p>Videos</p>
		</AccordionItem>
		<AccordionItem open title="Images">
            <Link href="/image">All</Link>
			<p>Images</p>
		</AccordionItem>
	{/await}
</Accordion>
