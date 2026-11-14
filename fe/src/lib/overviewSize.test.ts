import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	batchOf,
	clampLevel,
	clearSessionOverviewSize,
	currentOverviewSize,
	OVERVIEW_SIZES,
	sessionOverviewSize,
	setSessionOverviewSize,
	thumbRequestWidth
} from './overviewSize';
import { config } from './config.svelte';

function stubSessionStorage(initial: Record<string, string> = {}) {
	const store = new Map(Object.entries(initial));
	vi.stubGlobal('sessionStorage', {
		getItem: (k: string) => store.get(k) ?? null,
		setItem: (k: string, v: string) => store.set(k, v),
		removeItem: (k: string) => store.delete(k)
	});
	return store;
}

afterEach(() => {
	vi.unstubAllGlobals();
	config.overviewSize = 0;
});

describe('levels', () => {
	it('clamps to the defined sizes', () => {
		expect(clampLevel(-1)).toBe(0);
		expect(clampLevel(99)).toBe(OVERVIEW_SIZES.length - 1);
		expect(clampLevel(NaN)).toBe(0);
		expect(clampLevel(1.4)).toBe(1);
	});

	it('grow tiles and shrink batches from S to XL', () => {
		for (let i = 1; i < OVERVIEW_SIZES.length; i++) {
			const prev = OVERVIEW_SIZES[i - 1];
			const cur = OVERVIEW_SIZES[i];
			expect(cur.minWidthRem).toBeGreaterThan(prev.minWidthRem);
			expect(cur.thumb).toBeGreaterThan(prev.thumb);
			expect(cur.mobileColumns).toBeLessThan(prev.mobileColumns);
			expect(cur.batch).toBeLessThan(prev.batch);
		}
	});
});

describe('thumbRequestWidth', () => {
	it('keeps the original 200px at S on a 1x screen', () => {
		expect(thumbRequestWidth(200, 1)).toBe(200);
	});

	it('snaps up to a fixed width', () => {
		expect(thumbRequestWidth(250, 1)).toBe(320);
		expect(thumbRequestWidth(320, 1.5)).toBe(480);
	});

	it('caps the pixel ratio at 2 and the width at the largest step', () => {
		expect(thumbRequestWidth(480, 3)).toBe(960);
		expect(thumbRequestWidth(5000, 1)).toBe(2048);
	});

	it('treats a ratio below 1 as 1', () => {
		expect(thumbRequestWidth(200, 0.5)).toBe(200);
	});
});

describe('batchOf', () => {
	it('finds the 1-based batch of a page', () => {
		expect(batchOf(1, 60)).toBe(1);
		expect(batchOf(60, 60)).toBe(1);
		expect(batchOf(61, 60)).toBe(2);
		expect(batchOf(25, 12)).toBe(3);
	});

	it('puts page 0 (nothing open yet) in the first batch', () => {
		expect(batchOf(0, 24)).toBe(1);
	});
});

describe('session size', () => {
	it('falls back to the saved default', () => {
		stubSessionStorage();
		config.overviewSize = 2;
		expect(sessionOverviewSize()).toBeNull();
		expect(currentOverviewSize()).toBe(2);
	});

	it('overrides the default for the session', () => {
		const store = stubSessionStorage();
		config.overviewSize = 0;
		setSessionOverviewSize(3);
		expect(store.get('organizer.overviewSize')).toBe('3');
		expect(currentOverviewSize()).toBe(3);
		clearSessionOverviewSize();
		expect(currentOverviewSize()).toBe(0);
	});

	it('ignores a stored value that is not a level', () => {
		stubSessionStorage({ 'organizer.overviewSize': '7' });
		expect(sessionOverviewSize()).toBeNull();
		stubSessionStorage({ 'organizer.overviewSize': 'big' });
		expect(sessionOverviewSize()).toBeNull();
	});

	it('works without storage', () => {
		vi.stubGlobal('sessionStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			},
			removeItem: () => {
				throw new Error('blocked');
			}
		});
		config.overviewSize = 1;
		expect(() => setSessionOverviewSize(2)).not.toThrow();
		expect(() => clearSessionOverviewSize()).not.toThrow();
		expect(currentOverviewSize()).toBe(1);
	});
});
