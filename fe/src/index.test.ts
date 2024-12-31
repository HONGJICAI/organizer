import { describe, it, expect } from 'vitest';
import { separateFilename } from './lib/utility';

describe('seperateFilename test', () => {
	it('simple filename', () => {
		expect(separateFilename('[a]b(c)')).toStrictEqual(['a', 'b', 'c']);
		expect(separateFilename('[a] b(c)')).toStrictEqual(['a', 'b', 'c']);
		expect(separateFilename('[a]b(c )')).toStrictEqual(['a', 'b', 'c']);
	});
	it('nest filename', () => {
		expect(separateFilename('[a(b)]c')).toStrictEqual(['a(b)', 'c']);
	});
});
