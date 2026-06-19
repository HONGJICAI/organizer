import { describe, it, expect } from 'vitest';
import { stepPage } from './reader';

describe('stepPage (clamping, used by tap/click navigation)', () => {
	const max = 10;

	it('advances within range', () => {
		expect(stepPage(1, max, 1)).toBe(2);
		expect(stepPage(8, max, 1)).toBe(9);
	});

	it('reaches the last page instead of skipping it', () => {
		// Regression: 0-based modulo math used to jump 9 -> 0 here.
		expect(stepPage(9, max, 1)).toBe(10);
	});

	it('goes back within range', () => {
		expect(stepPage(10, max, -1)).toBe(9);
		expect(stepPage(2, max, -1)).toBe(1);
	});

	it('returns the same page at the boundaries (no-op signal)', () => {
		// Callers use the unchanged value to avoid getting stuck loading.
		expect(stepPage(10, max, 1)).toBe(10);
		expect(stepPage(1, max, -1)).toBe(1);
	});

	it('never produces the invalid page 0', () => {
		for (let p = 1; p <= max; p++) {
			expect(stepPage(p, max, 1)).toBeGreaterThanOrEqual(1);
			expect(stepPage(p, max, -1)).toBeGreaterThanOrEqual(1);
		}
	});

	it('is a no-op when there are no pages', () => {
		expect(stepPage(1, 0, 1)).toBe(1);
		expect(stepPage(1, 0, -1)).toBe(1);
	});

	it('stays put on a single-page document', () => {
		expect(stepPage(1, 1, 1)).toBe(1);
		expect(stepPage(1, 1, -1)).toBe(1);
	});
});

describe('stepPage (looping, used by keyboard arrows)', () => {
	const max = 10;

	it('wraps forward off the last page', () => {
		expect(stepPage(9, max, 1, true)).toBe(10);
		expect(stepPage(10, max, 1, true)).toBe(1);
	});

	it('wraps backward off the first page', () => {
		// Regression: this used to land on the invalid page 0.
		expect(stepPage(1, max, -1, true)).toBe(10);
		expect(stepPage(10, max, -1, true)).toBe(9);
	});

	it('always stays in the 1..maxPage range', () => {
		for (let p = 1; p <= max; p++) {
			const next = stepPage(p, max, 1, true);
			const prev = stepPage(p, max, -1, true);
			expect(next).toBeGreaterThanOrEqual(1);
			expect(next).toBeLessThanOrEqual(max);
			expect(prev).toBeGreaterThanOrEqual(1);
			expect(prev).toBeLessThanOrEqual(max);
		}
	});

	it('does not divide by zero when there are no pages', () => {
		expect(stepPage(1, 0, 1, true)).toBe(1);
		expect(stepPage(1, 0, -1, true)).toBe(1);
	});
});
