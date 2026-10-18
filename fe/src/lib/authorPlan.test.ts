import { describe, expect, it } from 'vitest';
import { planAuthors } from './authorPlan';
import { TagIndex } from './tagIndex';

const index = new TagIndex([
	{ name: 'アリス', kind: 'author', canonical: null },
	{ name: 'Alice', kind: null, canonical: 'アリス' },
	{ name: 'Bob', kind: 'author', canonical: null },
	{ name: 'Carol', kind: 'circle', canonical: null }
]);

const file = (id: number, name: string, path: string, archived = false) => ({
	id,
	name,
	path,
	archived
});

describe('planAuthors', () => {
	it('groups by primary author and finds comics outside their folder', () => {
		const { authors, multi } = planAuthors(
			[
				file(1, '[アリス] One.zip', '/data/comics/アリス/[アリス] One.zip'),
				file(2, '[Alice] Two.zip', '/data/comics/inbox/[Alice] Two.zip'),
				file(3, '[Bob] Three.zip', '/data/comics/Bob/[Bob] Three.zip'),
				file(4, '[Bob] [アリス] Four.zip', '/data/comics/inbox/[Bob] [アリス] Four.zip'),
				file(5, '[Carol] Five.zip', '/data/comics/inbox/[Carol] Five.zip'),
				file(6, '[Bob] Gone.zip', '/data/comics/inbox/[Bob] Gone.zip', true)
			],
			index
		);
		expect(authors).toEqual([
			{ author: 'アリス', ids: [1, 2], outside: [2] },
			{ author: 'Bob', ids: [3], outside: [] }
		]);
		expect(multi).toEqual([{ id: 4, name: '[Bob] [アリス] Four.zip', authors: ['Bob', 'アリス'] }]);
	});

	it('compares folders by the sanitized folder name', () => {
		const slash = new TagIndex([{ name: 'A:B', kind: 'author', canonical: null }]);
		const { authors } = planAuthors(
			[file(1, '[A:B] x.zip', '/data/comics/A_B/[A:B] x.zip')],
			slash
		);
		expect(authors[0].outside).toEqual([]);
	});
});
