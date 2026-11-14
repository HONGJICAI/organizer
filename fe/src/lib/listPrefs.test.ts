import { afterEach, describe, expect, it, vi } from 'vitest';
import { effectiveOrderBy, loadListPrefs, saveListPrefs } from './listPrefs';

const DEFAULTS = { orderBy: 2, reverse: true, unreadOnly: false, includeSub: false };

function stubSessionStorage(initial: Record<string, string> = {}) {
	const store = new Map(Object.entries(initial));
	vi.stubGlobal('sessionStorage', {
		getItem: (k: string) => store.get(k) ?? null,
		setItem: (k: string, v: string) => store.set(k, v),
		removeItem: (k: string) => store.delete(k)
	});
	return store;
}

afterEach(() => vi.unstubAllGlobals());

describe('list prefs', () => {
	it('start from the defaults', () => {
		stubSessionStorage();
		expect(loadListPrefs('comic', DEFAULTS)).toEqual(DEFAULTS);
	});

	it('round-trip per list', () => {
		stubSessionStorage();
		saveListPrefs('comic', { orderBy: 1, reverse: false, unreadOnly: true, includeSub: false });
		expect(loadListPrefs('comic', DEFAULTS)).toEqual({
			orderBy: 1,
			reverse: false,
			unreadOnly: true,
			includeSub: false
		});
		expect(loadListPrefs('image', DEFAULTS)).toEqual(DEFAULTS);
		expect(loadListPrefs('comic.folder', DEFAULTS)).toEqual(DEFAULTS);
	});

	it('fall back field by field on bad data', () => {
		stubSessionStorage({
			'organizer.list.comic': JSON.stringify({ orderBy: 'name', reverse: false, unreadOnly: 1 })
		});
		expect(loadListPrefs('comic', DEFAULTS)).toEqual({ ...DEFAULTS, reverse: false });
		stubSessionStorage({ 'organizer.list.comic': 'not json' });
		expect(loadListPrefs('comic', DEFAULTS)).toEqual(DEFAULTS);
	});

	it('work without storage', () => {
		vi.stubGlobal('sessionStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		expect(() => saveListPrefs('comic', DEFAULTS)).not.toThrow();
		expect(loadListPrefs('comic', DEFAULTS)).toEqual(DEFAULTS);
	});
});

describe('effectiveOrderBy', () => {
	const all = [{ value: 1 }, { value: 2 }, { value: 100 }];
	it('keeps a key the list offers', () => {
		expect(effectiveOrderBy(100, all)).toBe(100);
	});
	it("uses the list's first key otherwise (Recent offers only view date)", () => {
		expect(effectiveOrderBy(100, [{ value: 3 }])).toBe(3);
	});
	it('keeps the chosen key while there are no options yet', () => {
		expect(effectiveOrderBy(100, [])).toBe(100);
	});
});
