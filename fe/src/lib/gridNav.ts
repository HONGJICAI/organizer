// Moving a selection around a wrapped grid of cards with the arrow keys, by
// where the cards are on screen rather than by a column count: the list wraps
// cards with flexbox, and the folder page stacks a grid of folder tiles (a
// different size) above its cards.

export interface Box {
	top: number;
	left: number;
	width: number;
	height: number;
}

export type Direction = 'left' | 'right' | 'up' | 'down';

/**
 * The index to move to from `from`, in document order. Returns -1 when the
 * move runs off the start and `boxes.length` when it runs off the end, so the
 * caller can go on to the previous or next page.
 */
export function gridStep(boxes: Box[], from: number, dir: Direction): number {
	if (dir === 'left') return from - 1;
	if (dir === 'right') return from + 1;
	const cur = boxes[from];
	const centre = cur.left + cur.width / 2;
	// Another row starts more than half the current box's height away.
	const rows = boxes
		.map((box, index) => ({ box, index }))
		.filter(({ box }) =>
			dir === 'down' ? box.top > cur.top + cur.height / 2 : box.top < cur.top - cur.height / 2
		);
	if (rows.length === 0) return dir === 'down' ? boxes.length : -1;
	const rowTop =
		dir === 'down'
			? Math.min(...rows.map(({ box }) => box.top))
			: Math.max(...rows.map(({ box }) => box.top));
	const row = rows.filter(({ box }) => Math.abs(box.top - rowTop) < Math.max(1, box.height / 2));
	let best = row[0];
	for (const candidate of row) {
		const distance = Math.abs(candidate.box.left + candidate.box.width / 2 - centre);
		if (distance < Math.abs(best.box.left + best.box.width / 2 - centre)) best = candidate;
	}
	return best.index;
}
