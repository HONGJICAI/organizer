import { describe, expect, it } from 'vitest';
import { ComicComparison, Image, MediaType, VideoComparison } from '$lib/model.svelte';
import type { ImageEntity } from '$lib/client';
import { getOrderByOptions } from './orderByOptions';

const values = (type: MediaType) => getOrderByOptions(type).map((o) => o.value);

describe('getOrderByOptions', () => {
	it('offers page count for image albums, not size per page', () => {
		expect(values(MediaType.Image)).toContain(ComicComparison.Page);
		expect(values(MediaType.Image)).not.toContain(ComicComparison.SizePerPage);
	});

	it('keeps the type-specific options to their type', () => {
		expect(values(MediaType.Comic)).toEqual(
			expect.arrayContaining([ComicComparison.Page, ComicComparison.SizePerPage])
		);
		expect(values(MediaType.Video)).not.toContain(ComicComparison.Page);
		expect(values(MediaType.Video)).toContain(VideoComparison.Duration);
	});
});

describe('Image.compareTo', () => {
	const album = (id: number, page: number) =>
		new Image({
			id,
			name: `album ${id}`,
			path: `/data/images/${id}`,
			size: 0,
			updateTime: '2026-01-01T00:00:00',
			page
		} as ImageEntity);

	it('sorts albums by page count', () => {
		const sorted = [album(1, 30), album(2, 5), album(3, 12)].sort((a, b) =>
			a.compareTo(b, ComicComparison.Page)
		);
		expect(sorted.map((a) => a.page)).toEqual([5, 12, 30]);
	});
});
