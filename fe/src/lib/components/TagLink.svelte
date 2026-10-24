<script lang="ts">
	import { Tag } from 'carbon-components-svelte';
	import type { Snippet } from 'svelte';
	import { newTabHref } from '$lib/links';

	// A Carbon tag that is a real link, so middle-click and "open in new tab"
	// work. `newTab` opens it in a new tab on a plain click too.

	type TagType = 'purple' | 'magenta' | 'cyan' | 'gray' | 'teal' | 'cool-gray' | 'blue' | 'green';
	interface Props {
		href: string;
		newTab?: boolean;
		type?: TagType;
		title?: string;
		children: Snippet;
	}
	let { href, newTab = false, type, title, children }: Props = $props();
</script>

<a
	class="tag-link"
	href={newTab ? newTabHref(href) : href}
	target={newTab ? '_blank' : undefined}
	rel={newTab ? 'noopener' : undefined}
	{title}
>
	<Tag {type}>{@render children()}</Tag>
</a>

<style>
	.tag-link {
		display: inline-flex;
		max-width: 100%;
		text-decoration: none;
	}
	.tag-link :global(.bx--tag) {
		cursor: pointer;
	}
	.tag-link:hover :global(.bx--tag),
	.tag-link:focus-visible :global(.bx--tag) {
		filter: brightness(1.25);
	}
</style>
