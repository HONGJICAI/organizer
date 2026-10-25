import { describe, expect, it } from 'vitest';
import type { ComicEntity, VideoEntity } from '$lib/client';
import { Comic, ComicComparison, Video, VideoComparison, perUnit } from '$lib/model.svelte';

const MB = 1024 * 1024;
const comic = (id: number, mb: number, page: number) =>
	new Comic({
		id,
		name: `${id}`,
		path: `/${id}`,
		size: mb * MB,
		page,
		updateTime: '2024-01-01'
	} as ComicEntity);

describe('size-per-unit sorting', () => {
	it('keeps items without pages or duration out of NaN', () => {
		expect(perUnit(10, 2)).toBe(5);
		expect(perUnit(0, 0)).toBe(-1);
		expect(perUnit(10, 0)).toBe(-1);
	});

	it('sorts comics by size per page, ones without pages last', () => {
		// 0/0 and x/0 pages used to give NaN comparisons: an unordered list
		// that reshuffled whenever a comic was removed.
		const comics = [
			comic(1, 10, 10),
			comic(2, 0, 0),
			comic(3, 30, 10),
			comic(4, 5, 0),
			comic(5, 20, 10),
			comic(6, 0, 0)
		];
		const order = (list: Comic[]) =>
			list
				.slice()
				.sort((a, b) => -a.compareTo(b, ComicComparison.SizePerPage))
				.map((c) => c.id);
		const before = order(comics);
		expect(before).toEqual([3, 5, 1, 2, 4, 6]);
		for (const id of before) {
			expect(order(comics.filter((c) => c.id !== id))).toEqual(before.filter((i) => i !== id));
		}
	});

	it('sorts videos without a duration below the rest', () => {
		const video = (id: number, mb: number, durationInSecond: number) =>
			new Video({
				id,
				name: `${id}`,
				path: `/${id}`,
				size: mb * MB,
				durationInSecond,
				updateTime: '2024-01-01'
			} as VideoEntity);
		const [a, b, none] = [video(1, 10, 10), video(2, 30, 10), video(3, 50, 0)];
		expect(b.compareTo(a, VideoComparison.SizePerSecond)).toBeGreaterThan(0);
		expect(none.compareTo(a, VideoComparison.SizePerSecond)).toBeLessThan(0);
		expect(none.compareTo(video(4, 9, 0), VideoComparison.SizePerSecond)).toBe(0);
	});
});
