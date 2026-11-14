import { describe, expect, it } from 'vitest';
import { gridStep, type Box } from './gridNav';

// A wrapped grid: `count` boxes of w×h, `cols` per row, gap 10.
function grid(count: number, cols: number, w = 100, h = 150, offsetTop = 0): Box[] {
	return Array.from({ length: count }, (_, i) => ({
		left: (i % cols) * (w + 10),
		top: offsetTop + Math.floor(i / cols) * (h + 10),
		width: w,
		height: h
	}));
}

describe('gridStep', () => {
	const boxes = grid(10, 4); // rows: 0-3, 4-7, 8-9

	it('moves left and right in document order, across rows', () => {
		expect(gridStep(boxes, 5, 'right')).toBe(6);
		expect(gridStep(boxes, 3, 'right')).toBe(4);
		expect(gridStep(boxes, 4, 'left')).toBe(3);
	});

	it('reports running off either end', () => {
		expect(gridStep(boxes, 0, 'left')).toBe(-1);
		expect(gridStep(boxes, 9, 'right')).toBe(10);
		expect(gridStep(boxes, 1, 'up')).toBe(-1);
		expect(gridStep(boxes, 8, 'down')).toBe(10);
	});

	it('moves up and down within the same column', () => {
		expect(gridStep(boxes, 1, 'down')).toBe(5);
		expect(gridStep(boxes, 6, 'up')).toBe(2);
	});

	it('goes to the nearest box of a short last row', () => {
		expect(gridStep(boxes, 7, 'down')).toBe(9);
		expect(gridStep(boxes, 5, 'down')).toBe(9);
		expect(gridStep(boxes, 4, 'down')).toBe(8);
	});

	it('crosses between grids of different sizes (folder tiles above cards)', () => {
		const tiles = grid(3, 3, 200, 60);
		const cards = grid(4, 4, 100, 150, 80);
		const all = [...tiles, ...cards];
		// down from the middle tile (centre x 310) lands on the card nearest it (centre 270)
		expect(gridStep(all, 1, 'down')).toBe(3 + 2);
		// up from the first card goes to the tile above it
		expect(gridStep(all, 3, 'up')).toBe(0);
	});
});
