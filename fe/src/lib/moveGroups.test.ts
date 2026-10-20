import { describe, expect, it } from 'vitest';
import { authorGroups, tagGroup } from './moveGroups';
import { TagIndex } from './tagIndex';

const index = new TagIndex([
	{ name: 'アリス', kind: 'author', canonical: null },
	{ name: 'Alice', kind: null, canonical: 'アリス' },
	{ name: 'Bob', kind: 'author', canonical: null },
	{ name: 'Carol', kind: 'language', canonical: null }
]);

const file = (id: number, name: string, path: string, archived = false) => ({
	id,
	name,
	path,
	archived
});

const files = [
	file(1, '[アリス] One.zip', '/data/comics/アリス/[アリス] One.zip'),
	file(2, '[Alice] Two.zip', '/data/comics/inbox/[Alice] Two.zip'),
	file(3, '[Bob] Three.zip', '/data/comics/Bob/[Bob] Three.zip'),
	file(4, '[Bob] [アリス] Four.zip', '/data/comics/inbox/[Bob] [アリス] Four.zip'),
	file(5, '[Carol] Five.zip', '/data/comics/inbox/[Carol] Five.zip'),
	file(6, '[Bob] Gone.zip', '/data/comics/inbox/[Bob] Gone.zip', true)
];

describe('authorGroups', () => {
	it('groups by primary author, work first', () => {
		const groups = authorGroups(files, index);
		expect(groups.map((g) => [g.key, g.pending])).toEqual([
			['アリス', [2]],
			['Bob', []]
		]);
		const alice = groups[0];
		expect(alice.names).toEqual(['アリス', 'Alice']);
		expect(alice.isAuthor).toBe(true);
		expect(alice.comics.map((c) => [c.id, c.inPlace, c.otherAuthors])).toEqual([
			[1, true, []],
			[2, false, []],
			[4, false, ['Bob']]
		]);
		expect(alice.comics[1].folder).toBe('/data/comics/inbox');
	});

	it('compares folders by the sanitized folder name', () => {
		const odd = new TagIndex([{ name: 'A:B', kind: 'author', canonical: null }]);
		const [group] = authorGroups([file(1, '[A:B] x.zip', '/data/comics/A_B/[A:B] x.zip')], odd);
		expect(group.pending).toEqual([]);
	});
});

describe('tagGroup', () => {
	it('takes any tag with its aliases', () => {
		const carol = tagGroup(files, index, ' Carol ');
		expect(carol?.isAuthor).toBe(false);
		expect(carol?.pending).toEqual([5]);
		expect(tagGroup(files, index, 'Alice')?.key).toBe('アリス');
		expect(tagGroup(files, index, 'Alice')?.comics.map((c) => c.id)).toEqual([1, 2, 4]);
	});

	it('is null without comics', () => {
		expect(tagGroup(files, index, 'Nobody')).toBeNull();
		expect(tagGroup(files, index, ' ')).toBeNull();
	});
});

describe('in place', () => {
	it('ignores case and Unicode normalization of the folder', () => {
		const idx = new TagIndex([{ name: 'Hoge', kind: 'author', canonical: null }]);
		const [group] = authorGroups(
			[
				file(1, '[Hoge] a.zip', '/data/comics/artist/hoge/[Hoge] a.zip'),
				file(2, '[Hoge] b.zip', '/data/comics/inbox/[Hoge] b.zip')
			],
			idx
		);
		expect(group.comics.map((c) => c.inPlace)).toEqual([true, false]);
		const nfd = 'が'.normalize('NFD');
		const kana = new TagIndex([{ name: 'が', kind: 'author', canonical: null }]);
		const [g2] = authorGroups([file(3, '[が] c.zip', `/data/comics/${nfd}/[が] c.zip`)], kana);
		expect(g2.pending).toEqual([]);
	});
});
