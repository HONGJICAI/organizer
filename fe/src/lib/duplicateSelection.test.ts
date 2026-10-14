import { describe, expect, it } from 'vitest';
import {
	clearGroup,
	filterGroups,
	keepOnly,
	pageMismatch,
	reclaimable,
	selectedIn,
	sortBySavings,
	suggestedSelection
} from './duplicateSelection';

const a = {
	keepId: 1,
	items: [
		{ id: 1, favorited: false },
		{ id: 2, favorited: false },
		{ id: 3, favorited: true }
	]
};
const b = {
	keepId: 5,
	items: [
		{ id: 4, favorited: false },
		{ id: 5, favorited: false }
	]
};

describe('suggestedSelection', () => {
	it('selects everything but the keeper and favorites', () => {
		expect([...suggestedSelection([a, b])].sort()).toEqual([2, 4]);
	});

	it('is empty without groups', () => {
		expect(suggestedSelection([]).size).toBe(0);
	});
});

describe('keepOnly', () => {
	it('selects the rest of the group except favorites', () => {
		const next = keepOnly(new Set([2, 4]), a, 2);
		expect([...next].sort()).toEqual([1, 4]);
	});

	it('does not mutate the input', () => {
		const sel = new Set([4]);
		keepOnly(sel, a, 1);
		expect([...sel]).toEqual([4]);
	});
});

describe('clearGroup', () => {
	it('deselects only that group', () => {
		expect([...clearGroup(new Set([1, 2, 4]), a)]).toEqual([4]);
	});
});

const sized = (
	id: number,
	size: number,
	page = 10,
	favorited = false
): { id: number; size: number; page: number; favorited: boolean } => ({
	id,
	size,
	page,
	favorited
});

const small = { exact: true, keepId: 1, items: [sized(1, 5), sized(2, 3)] };
const big = {
	exact: false,
	keepId: 4,
	items: [sized(3, 20), sized(4, 30), sized(5, 50, 10, true)]
};

describe('filterGroups', () => {
	it('keeps all, exact or similar groups', () => {
		expect(filterGroups([small, big], 'all')).toEqual([small, big]);
		expect(filterGroups([small, big], 'exact')).toEqual([small]);
		expect(filterGroups([small, big], 'similar')).toEqual([big]);
	});
});

describe('reclaimable', () => {
	it('sums deletable copies, skipping the keeper and favorites', () => {
		expect(reclaimable(small)).toBe(3);
		expect(reclaimable(big)).toBe(20);
	});
});

describe('sortBySavings', () => {
	it('orders groups by reclaimable space and copies by size', () => {
		const sorted = sortBySavings([small, big]);
		expect(sorted.map((g) => g.keepId)).toEqual([4, 1]);
		expect(sorted[0].items.map((c) => c.id)).toEqual([5, 4, 3]);
	});

	it('does not mutate the input', () => {
		sortBySavings([small, big]);
		expect(big.items.map((c) => c.id)).toEqual([3, 4, 5]);
	});
});

describe('pageMismatch', () => {
	it('flags a 1.5x page spread', () => {
		expect(pageMismatch({ ...small, items: [sized(1, 1, 20), sized(2, 1, 30)] })).toBe(true);
		expect(pageMismatch({ ...small, items: [sized(1, 1, 20), sized(2, 1, 29)] })).toBe(false);
	});

	it('ignores unknown page counts', () => {
		expect(pageMismatch({ ...small, items: [sized(1, 1, 0), sized(2, 1, 30)] })).toBe(false);
	});
});

describe('selectedIn', () => {
	it('returns only selections inside the given groups', () => {
		expect(selectedIn(new Set([2, 3, 99]), [small])).toEqual([2]);
	});
});
