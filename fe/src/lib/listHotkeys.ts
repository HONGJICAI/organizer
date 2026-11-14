// Keyboard shortcuts for pages that show a paginated grid of cards (the media
// lists and the folder page). Arrows move the focused card, carrying on into
// the next or previous list page; PageDown/PageUp scroll a screen at a time
// and change pages only from the bottom/top; Enter opens the focused card
// (cards handle it themselves). Works like the reader's page overview.
//
// Cards opt in with a `data-nav-item` attribute and must be focusable.

import { tick } from 'svelte';
import { gridStep, type Direction } from '$lib/gridNav';
import { Layer, registerHotkeys, type Hotkey } from '$lib/hotkeys';
import { InfoNotification } from '$lib/model.svelte';
import { addNotificationOnce } from '$lib/state.svelte';

export interface ListNav {
	page: () => number;
	totalPages: () => number;
	// Show a list page; resolves once the navigation is done.
	goToPage: (page: number) => Promise<unknown> | unknown;
	// The search box, for '/'.
	search?: () => HTMLInputElement | null | undefined;
	// Category tabs, for the number keys.
	categories?: { names: string[]; select: (index: number) => void };
}

const SELECTOR = '[data-nav-item]';

// Cards on screen now, in document order. Cards still fading out after a page
// change are skipped by the caller, see focusNew.
function items(): HTMLElement[] {
	return Array.from(document.querySelectorAll<HTMLElement>(SELECTOR)).filter(
		(el) => el.offsetParent !== null
	);
}

// The fixed Carbon header covers the top of the window.
function headerBottom(): number {
	return document.querySelector('.bx--header')?.getBoundingClientRect().bottom ?? 0;
}

function focusItem(el: HTMLElement | undefined) {
	if (!el) return;
	el.focus({ preventScroll: true });
	const top = headerBottom();
	const r = el.getBoundingClientRect();
	if (r.top < top) window.scrollBy({ top: r.top - top - 8, behavior: 'instant' });
	else if (r.bottom > window.innerHeight)
		window.scrollBy({ top: r.bottom - window.innerHeight + 8, behavior: 'instant' });
}

function lastPageNotice(nav: ListNav) {
	const n = nav.totalPages();
	addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: `Page ${n} of ${n}` }));
}

export function registerListHotkeys(nav: ListNav): () => void {
	// Show another list page, then focus its first or last card. Cards of the
	// old page may still be fading out, so only cards that weren't there before
	// count.
	async function showPage(page: number, focus: 'first' | 'last') {
		let fresh: HTMLElement[];
		if (page === nav.page()) {
			fresh = items();
		} else {
			const before = new Set(items());
			await nav.goToPage(page);
			await tick();
			fresh = items().filter((el) => !before.has(el));
		}
		if (focus === 'first') {
			window.scrollTo({ top: 0, behavior: 'instant' });
			fresh[0]?.focus({ preventScroll: true });
		} else {
			window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
			fresh[fresh.length - 1]?.focus({ preventScroll: true });
		}
	}

	function move(dir: Direction) {
		const list = items();
		if (list.length === 0) return;
		const from = list.indexOf(document.activeElement as HTMLElement);
		if (from === -1) {
			// Nothing selected: pick up at the card selected last (focus is lost when
			// the detail dialog or the reader closes), else the first card in view.
			const top = headerBottom();
			focusItem(
				(lastSelected && list.includes(lastSelected) ? lastSelected : undefined) ??
					list.find((el) => el.getBoundingClientRect().bottom > top) ??
					list[0]
			);
			return;
		}
		const to = gridStep(
			list.map((el) => el.getBoundingClientRect()),
			from,
			dir
		);
		if (to >= 0 && to < list.length) focusItem(list[to]);
		else if (to >= list.length) {
			if (nav.page() < nav.totalPages()) showPage(nav.page() + 1, 'first');
			else lastPageNotice(nav);
		} else if (nav.page() > 1) showPage(nav.page() - 1, 'last');
	}

	// Scroll the window a screen at a time: the first card cut off at the bottom
	// moves to the top (or, going back, the last one cut off at the top to the
	// bottom), and it gets the focus. From the very bottom/top, change page.
	function pageScroll(delta: 1 | -1) {
		const top = headerBottom();
		const root = document.documentElement;
		const atEdge =
			delta > 0
				? window.scrollY + window.innerHeight >= root.scrollHeight - 2
				: window.scrollY <= 2;
		if (atEdge) {
			if (delta > 0) {
				if (nav.page() < nav.totalPages()) showPage(nav.page() + 1, 'first');
				else lastPageNotice(nav);
			} else if (nav.page() > 1) showPage(nav.page() - 1, 'last');
			return;
		}
		const list = items();
		const screen = window.innerHeight - top;
		if (delta > 0) {
			const target = list.find((el) => el.getBoundingClientRect().bottom > window.innerHeight + 1);
			const by = target ? target.getBoundingClientRect().top - top - 8 : screen;
			window.scrollBy({ top: by > 0 ? by : screen, behavior: 'instant' });
			target?.focus({ preventScroll: true });
		} else {
			const target = list.filter((el) => el.getBoundingClientRect().top < top - 1).pop();
			const by = target ? target.getBoundingClientRect().bottom - window.innerHeight - 8 : -screen;
			window.scrollBy({ top: by < 0 ? by : -screen, behavior: 'instant' });
			target?.focus({ preventScroll: true });
		}
	}

	const hotkeys: Hotkey[] = [
		{ keys: ['ArrowLeft'], description: 'Previous item', run: () => move('left'), repeat: true },
		{ keys: ['ArrowRight'], description: 'Next item', run: () => move('right'), repeat: true },
		{ keys: ['ArrowUp'], description: 'Item above', run: () => move('up'), repeat: true },
		{ keys: ['ArrowDown'], description: 'Item below', run: () => move('down'), repeat: true },
		{ keys: ['Enter'], description: 'Open the selected item' },
		{
			keys: ['PageDown'],
			description: 'Next screen, then next page',
			run: () => pageScroll(1),
			repeat: true
		},
		{
			keys: ['PageUp'],
			description: 'Previous screen, then previous page',
			run: () => pageScroll(-1),
			repeat: true
		},
		{ keys: ['Home'], description: 'First page', run: () => showPage(1, 'first') },
		{
			keys: ['End'],
			description: 'Last page',
			run: () => showPage(Math.max(1, nav.totalPages()), 'first')
		}
	];
	if (nav.search) {
		const search = nav.search;
		hotkeys.push({
			keys: ['/'],
			description: 'Search',
			run: () => {
				const input = search();
				input?.focus();
				input?.select();
			}
		});
	}
	if (nav.categories) {
		const { names, select } = nav.categories;
		hotkeys.push({
			keys: names.map((_, i) => String(i + 1)),
			description: `Switch tab: ${names.join(', ')}`,
			run: (e) => select(Number(e.key) - 1)
		});
	}
	let lastSelected: HTMLElement | null = null;
	const remember = (e: FocusEvent) => {
		const el = (e.target as HTMLElement | null)?.closest?.(SELECTOR);
		if (el) lastSelected = el as HTMLElement;
	};
	document.addEventListener('focusin', remember);
	const unregister = registerHotkeys(Layer.Page, hotkeys);
	return () => {
		document.removeEventListener('focusin', remember);
		unregister();
	};
}
