import { describe, expect, it } from 'vitest';
import { hasTag } from './moveTarget';

describe('hasTag', () => {
	it('matches whole tags only', () => {
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', 'Alice')).toBe(true);
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', ' Parody ')).toBe(true);
		expect(hasTag('[Alicetta] Title.zip', 'Alice')).toBe(false);
		expect(hasTag('[Alice] Title.zip', '')).toBe(false);
	});
});
