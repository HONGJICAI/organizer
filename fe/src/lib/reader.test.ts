import { describe, expect, it } from 'vitest';
import { MediaType } from './model.svelte';
import { readerPath } from './reader';

describe('readerPath', () => {
	it('opens at page 1 without params', () => {
		expect(readerPath(MediaType.Comic, 7)).toBe('/comic/7');
		expect(readerPath(MediaType.Comic, 7, { page: 1 })).toBe('/comic/7');
	});

	it('carries the page and the overview', () => {
		expect(readerPath(MediaType.Comic, 7, { page: 22 })).toBe('/comic/7?page=22');
		expect(readerPath(MediaType.Image, 3, { page: 22, overview: true })).toBe(
			'/image/3?page=22&overview=1'
		);
		expect(readerPath(MediaType.Image, 3, { overview: true })).toBe('/image/3?overview=1');
	});
});
