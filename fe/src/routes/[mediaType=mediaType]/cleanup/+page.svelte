<script lang="ts">
	import BadNames from '$lib/components/BadNames.svelte';
	import MissingFiles from '$lib/components/MissingFiles.svelte';
	import NormalizeNames from '$lib/components/NormalizeNames.svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { Breadcrumb, BreadcrumbItem, Tab, TabContent, Tabs } from 'carbon-components-svelte';
	import { Home } from 'carbon-icons-svelte';

	// Library problems to fix by hand, one tab each; ?tab= picks one.
	let { data } = $props();
	let mediaType = $derived(page.params.mediaType ?? 'comic');
	const tabs = ['missing', 'names', 'normalize'] as const;
	let selected = $derived(Math.max(0, tabs.indexOf(page.url.searchParams.get('tab') as never)));

	function select(index: number) {
		if (index === selected) return;
		const url = new URL(page.url);
		url.searchParams.set('tab', tabs[index]);
		goto(url, { replaceState: true, keepFocus: true, noScroll: true });
	}
</script>

<Breadcrumb noTrailingSlash>
	<BreadcrumbItem href="/{mediaType}">
		<span class="crumb"><Home size={16} /><span>{mediaType}</span></span>
	</BreadcrumbItem>
	<BreadcrumbItem isCurrentPage>Cleanup</BreadcrumbItem>
</Breadcrumb>
<h1>Cleanup</h1>

<Tabs {selected} on:change={(e) => select(e.detail)}>
	<Tab label="Missing files" />
	<Tab label="Bad names" />
	<Tab label="Normalize" />
	<svelte:fragment slot="content">
		<TabContent>
			{#if selected === 0}<MissingFiles {mediaType} />{/if}
		</TabContent>
		<TabContent>
			{#if selected === 1}<BadNames {mediaType} files={data.files} />{/if}
		</TabContent>
		<TabContent>
			{#if selected === 2}<NormalizeNames {mediaType} files={data.files} />{/if}
		</TabContent>
	</svelte:fragment>
</Tabs>

<style>
	.crumb {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}
</style>
