import { describe, expect, it } from 'vitest';
import {
	compact,
	formatBytes,
	labelEvery,
	monthLabel,
	monthTitle,
	niceBytes,
	niceMax
} from './stats';

describe('formatBytes', () => {
	it('picks a unit and precision', () => {
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(512)).toBe('512 B');
		expect(formatBytes(1536)).toBe('1.50 KB');
		expect(formatBytes(15 * 1024 * 1024)).toBe('15.0 MB');
		expect(formatBytes(300 * 1024 ** 3)).toBe('300 GB');
		expect(formatBytes(2 * 1024 ** 5)).toBe('2048 TB');
	});
});

describe('compact', () => {
	it('compacts from a thousand up', () => {
		expect(compact(999)).toBe('999');
		expect(compact(1000)).toBe('1K');
		expect(compact(1250)).toBe('1.3K');
		expect(compact(12_400)).toBe('12K');
		expect(compact(3_400_000)).toBe('3.4M');
	});
});

describe('niceMax', () => {
	it('rounds up to 1/2/5 steps', () => {
		expect(niceMax(0)).toBe(1);
		expect(niceMax(1)).toBe(1);
		expect(niceMax(3)).toBe(5);
		expect(niceMax(7)).toBe(10);
		expect(niceMax(120)).toBe(200);
		expect(niceMax(0.3)).toBe(0.5);
	});
});

describe('niceBytes', () => {
	it('rounds in the display unit', () => {
		expect(formatBytes(niceBytes(1.86 * 1024 ** 3))).toBe('2.00 GB');
		expect(formatBytes(niceBytes(300 * 1024 ** 2))).toBe('500 MB');
		expect(niceBytes(0)).toBe(1);
	});
});

describe('monthTitle', () => {
	it('spells out the month and year', () => {
		expect(monthTitle('2026-09')).toBe('September 2026');
	});
});

describe('monthLabel', () => {
	it('formats months', () => {
		expect(monthLabel('2026-01', false)).toBe('Jan');
		expect(monthLabel('2026-01', true)).toBe('Jan 26');
	});
});

describe('labelEvery', () => {
	it('shows all labels when they fit', () => {
		const show = labelEvery(6, 12);
		expect([0, 1, 2, 3, 4, 5].every(show)).toBe(true);
	});

	it('thins labels from the end', () => {
		const show = labelEvery(24, 8);
		expect([...Array(24).keys()].filter(show)).toEqual([2, 5, 8, 11, 14, 17, 20, 23]);
	});
});
