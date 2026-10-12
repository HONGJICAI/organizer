import { describe, expect, it } from 'vitest';
import { clearGroup, keepOnly, suggestedSelection } from './duplicateSelection';

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
