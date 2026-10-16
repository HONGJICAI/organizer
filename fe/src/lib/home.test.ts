import { describe, it, expect } from 'vitest';
import type { ComicEntity, HomeResponse, ImageEntity, VideoEntity } from '$lib/client';
import { MediaType } from '$lib/model.svelte';
import { homeRows, interleave, readerUrl, ROW_SIZE } from './home';

const base = (id: number, updateTime: string) => ({
	id,
	name: `f${id}`,
	path: `/p/${id}`,
	size: 1,
	updateTime
});
const comic = (id: number, updateTime: string, extra: Partial<ComicEntity> = {}): ComicEntity => ({
	...base(id, updateTime),
	page: 10,
	...extra
});
const video = (id: number, updateTime: string): VideoEntity => base(id, updateTime);
const image = (id: number, updateTime: string, extra: Partial<ImageEntity> = {}): ImageEntity => ({
	...base(id, updateTime),
	page: 5,
	...extra
});
const empty = { comics: [], videos: [], images: [] };

describe('homeRows', () => {
	it('merges types newest first', () => {
		const data: HomeResponse = {
			continueReading: {
				comics: [comic(1, '2024-01-01', { lastViewedTime: '2024-03-01', lastViewedPosition: 2 })],
				images: [image(2, '2024-01-01', { lastViewedTime: '2024-04-01', lastViewedPosition: 1 })]
			},
			recent: {
				comics: [comic(1, '2024-01-01')],
				videos: [video(3, '2024-02-01')],
				images: [image(2, '2024-01-15')]
			},
			favorites: empty,
			random: empty
		};
		const rows = homeRows(data);
		expect(rows.continueReading.map((f) => [f.type, f.id])).toEqual([
			[MediaType.Image, 2],
			[MediaType.Comic, 1]
		]);
		expect(rows.recent.map((f) => f.id)).toEqual([3, 2, 1]);
		expect(rows.favorites).toEqual([]);
	});

	it('caps each row', () => {
		const many = Array.from({ length: ROW_SIZE }, (_, i) => comic(i + 1, '2024-01-01'));
		const rows = homeRows({
			continueReading: empty,
			recent: { comics: many, videos: many.map((c) => video(c.id, c.updateTime)) },
			favorites: empty,
			random: { comics: many, images: [image(99, '2024-01-01')] }
		});
		expect(rows.recent).toHaveLength(ROW_SIZE);
		expect(rows.random).toHaveLength(ROW_SIZE);
		// The lone album still makes it into the random pick.
		expect(rows.random.some((f) => f.type === MediaType.Image)).toBe(true);
	});
});

describe('interleave', () => {
	it('takes from each list in turn', () => {
		expect(interleave([['a1', 'a2', 'a3'], [], ['b1']])).toEqual(['a1', 'b1', 'a2', 'a3']);
	});
});

describe('readerUrl', () => {
	it('resumes at the last read page', () => {
		const [file] = homeRows({
			continueReading: {
				comics: [comic(7, '2024-01-01', { lastViewedTime: '2024-01-02', lastViewedPosition: 4 })]
			},
			recent: empty,
			favorites: empty,
			random: empty
		}).continueReading;
		expect(readerUrl(file, true)).toBe('/comic/7?page=4');
		expect(readerUrl(file)).toBe('/comic/7');
	});
});
