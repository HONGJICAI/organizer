import { describe, expect, it } from 'vitest';
import {
	TagIndex,
	classifierRows,
	countTags,
	groupTags,
	matchesKeywords,
	primaryTags
} from './tagIndex';

const index = new TagIndex([
	{ name: 'アリス', kind: 'author', canonical: null },
	{ name: 'Alice', kind: null, canonical: 'アリス' },
	{ name: 'Chinese', kind: 'language', canonical: null },
	{ name: 'DL版', kind: 'ignored', canonical: null },
	{ name: 'Merged', kind: null, canonical: null },
	{ name: 'merged-alias', kind: null, canonical: 'Merged' }
]);

describe('TagIndex', () => {
	it('resolves aliases to their primary and its kind', () => {
		expect(index.canonical('Alice')).toBe('アリス');
		expect(index.kind('Alice')).toBe('author');
		expect(index.kind('アリス')).toBe('author');
		expect(index.kind('unknown')).toBeUndefined();
		expect(index.names('Alice')).toEqual(['アリス', 'Alice']);
		expect(index.names('unknown')).toEqual(['unknown']);
		expect(index.namesIgnoringCase('alice')).toEqual(['アリス', 'Alice']);
		expect(index.namesIgnoringCase('nobody')).toEqual(['nobody']);
		expect(index.row('DL版')?.kind).toBe('ignored');
		expect(index.size).toBe(6);
	});

	it('lists the names of a kind, aliases included', () => {
		expect(index.withKind('author')).toEqual(['アリス', 'Alice']);
		expect(index.withKind('language')).toEqual(['Chinese']);
	});
});

describe('counting and grouping', () => {
	const sources = [
		'[アリス] One [Chinese] [DL版].zip',
		'[Alice] Two.zip',
		'[Alice] (アリス) Three.zip',
		'[Bob Circle (Carol)] Four [Chinese].zip',
		'[merged-alias] Five'
	];

	it('counts a file once per primary tag and drops ignored tags', () => {
		expect(primaryTags(sources[2], index)).toEqual(['アリス', 'Three.zip']);
		const counts = countTags(sources, index);
		expect(counts.get('アリス')).toBe(3);
		expect(counts.has('Alice')).toBe(false);
		expect(counts.has('DL版')).toBe(false);
		expect(counts.get('Chinese')).toBe(2);
		expect(counts.get('Merged')).toBe(1);
	});

	it('groups by kind, unclassified under other', () => {
		const groups = groupTags(countTags(sources, index), index);
		expect([...groups.author.keys()]).toEqual(['アリス']);
		// "[Circle (Author)]" is one tag: brackets aren't split further.
		expect(groups.other.has('Bob Circle (Carol)')).toBe(true);
		expect([...groups.language.keys()]).toEqual(['Chinese']);
		expect(groups.other.has('Four')).toBe(true);
		expect(groups.other.has('Merged')).toBe(true);
		const withIgnored = groupTags(new Map([['DL版', 1]]), index);
		expect(withIgnored.other.size).toBe(0);
	});

	it('folds aliases into one classifier row per primary', () => {
		const rows = classifierRows(sources, index);
		const byName = new Map(rows.map((r) => [r.name, r]));
		expect(rows[0]).toEqual({
			name: 'アリス',
			count: 3,
			kind: 'author',
			aliases: [{ name: 'Alice', count: 2 }]
		});
		expect(byName.has('Alice')).toBe(false);
		// The primary isn't in any name, but its alias is.
		expect(byName.get('Merged')).toEqual({
			name: 'Merged',
			count: 1,
			kind: undefined,
			aliases: [{ name: 'merged-alias', count: 1 }]
		});
		expect(byName.get('DL版')?.kind).toBe('ignored');
		expect(byName.get('Chinese')?.aliases).toEqual([]);
	});

	it('lists aliases no file uses with a zero count', () => {
		const row = classifierRows(['[アリス] One.zip'], index).find((r) => r.name === 'アリス');
		expect(row?.aliases).toEqual([{ name: 'Alice', count: 0 }]);
	});
});

describe('matchesKeywords', () => {
	it('matches a classified keyword through its aliases', () => {
		expect(matchesKeywords('[alice] two.zip', ['アリス'], index)).toBe(true);
		expect(matchesKeywords('[アリス] one.zip', ['alice'], index)).toBe(true);
		expect(matchesKeywords('[alice] two.zip', ['アリス', 'two'], index)).toBe(true);
		expect(matchesKeywords('[alice] two.zip', ['アリス', 'three'], index)).toBe(false);
		expect(matchesKeywords('[bob] x.zip', ['アリス'], index)).toBe(false);
	});
});
