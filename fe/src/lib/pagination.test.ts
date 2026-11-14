import { describe, expect, it } from 'vitest';
import { paginationShown } from './pagination';

describe('paginationShown', () => {
	it('keeps five slots on a phone', () => {
		expect(paginationShown(390)).toBe(5);
		expect(paginationShown(320)).toBe(5);
	});

	it('shows more pages on a wide screen, up to eleven', () => {
		expect(paginationShown(1200)).toBe(11);
		expect(paginationShown(3840)).toBe(11);
	});

	it('grows in odd steps in between', () => {
		expect(paginationShown(480)).toBe(7);
		expect(paginationShown(576)).toBe(9);
		for (let w = 300; w <= 1400; w += 10) expect(paginationShown(w) % 2).toBe(1);
	});

	it('falls back to five without a width', () => {
		expect(paginationShown(undefined)).toBe(5);
		expect(paginationShown(0)).toBe(5);
		expect(paginationShown(NaN)).toBe(5);
	});
});
