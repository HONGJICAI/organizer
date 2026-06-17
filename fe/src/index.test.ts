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
	it('splits path on both separators', () => {
		expect(separateFilename('[a]b\\(c)d')).toStrictEqual(['a', 'b', 'c', 'd']);
		expect(separateFilename('/root/[a]b/(c)')).toStrictEqual(['root', 'a', 'b', 'c']);
		expect(separateFilename('C:\\media\\[a]b\\(c)')).toStrictEqual(['C:', 'media', 'a', 'b', 'c']);
	});
});
