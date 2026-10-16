// Selection helpers for the duplicate finder. Pure functions over plain data
// so they can be unit-tested without the page.

export interface DupItem {
	id: number;
	favorited: boolean;
}

export interface DupGroup<T extends DupItem = DupItem> {
	keepId: number;
	items: T[];
}

// Favorited comics are refused by the delete endpoint, so they are never
// selectable.
function deletable(items: DupItem[], keepId: number): number[] {
	return items.filter((c) => c.id !== keepId && !c.favorited).map((c) => c.id);
}

/** Every copy except each group's suggested keeper. */
export function suggestedSelection(groups: DupGroup[]): Set<number> {
	return new Set(groups.flatMap((g) => deletable(g.items, g.keepId)));
}

/** Select every copy in `group` except `keepId`, leaving other groups alone. */
export function keepOnly(selected: Set<number>, group: DupGroup, keepId: number): Set<number> {
	const next = clearGroup(selected, group);
	for (const id of deletable(group.items, keepId)) next.add(id);
	return next;
}

/** Deselect every copy in `group`, leaving other groups alone. */
export function clearGroup(selected: Set<number>, group: DupGroup): Set<number> {
	const next = new Set(selected);
	for (const c of group.items) next.delete(c.id);
	return next;
}

export type DupFilter = 'all' | 'exact' | 'similar';

export interface SizedItem extends DupItem {
	size: number;
	page: number;
}

export interface SizedGroup<T extends SizedItem = SizedItem> extends DupGroup<T> {
	exact: boolean;
}

/** Groups matching the exact/similar filter. */
export function filterGroups<G extends SizedGroup>(groups: G[], filter: DupFilter): G[] {
	if (filter === 'all') return groups;
	return groups.filter((g) => g.exact === (filter === 'exact'));
}

/** Total size of every copy in the group. */
export function groupSize(group: SizedGroup): number {
	return group.items.reduce((sum, c) => sum + c.size, 0);
}

/** Groups by total size, largest first; each group's copies largest first. */
export function sortBySize<G extends SizedGroup>(groups: G[]): G[] {
	return groups
		.map((g) => ({
			g: { ...g, items: [...g.items].sort((a, b) => b.size - a.size) },
			size: groupSize(g)
		}))
		.sort((a, b) => b.size - a.size)
		.map(({ g }) => g);
}

/**
 * Copies of one work should have about the same page count. A big spread
 * (largest ≥ 1.5× smallest) suggests the names matched but the books differ,
 * or one copy is incomplete. Unknown (0) page counts are ignored.
 */
export function pageMismatch(group: SizedGroup, ratio = 1.5): boolean {
	const pages = group.items.map((c) => c.page).filter((p) => p > 0);
	if (pages.length < 2) return false;
	return Math.max(...pages) >= Math.min(...pages) * ratio;
}

/** Ids in `selected` that belong to `groups` — what an action on the visible groups touches. */
export function selectedIn(selected: Set<number>, groups: DupGroup[]): number[] {
	return groups.flatMap((g) => g.items.filter((c) => selected.has(c.id)).map((c) => c.id));
}
