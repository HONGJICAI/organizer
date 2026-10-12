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
