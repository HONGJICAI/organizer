import { describe, it, expect, vi, beforeEach } from 'vitest';

// Stub the SDK so loaders never hit the network. Empty data arrays keep the
// focus on caching behaviour (no model construction needed).
const comicGetAll = vi.fn();
const videoGetAll = vi.fn();
const imageGetAll = vi.fn();

vi.mock('$lib/client/sdk.gen.js', () => ({
	ComicsService: { comicGetAll: () => comicGetAll() },
	VideosService: { videoGetAll: () => videoGetAll() },
	ImagesService: { imageGetAll: () => imageGetAll() }
}));

import { getMediaFiles, refreshMediaFiles } from './mediaStore';

beforeEach(() => {
	// The cache is module-scoped and shared across tests; clear it and reset the
	// loaders to a successful empty response.
	refreshMediaFiles();
	comicGetAll.mockReset().mockResolvedValue({ data: [], error: undefined });
	videoGetAll.mockReset().mockResolvedValue({ data: [], error: undefined });
	imageGetAll.mockReset().mockResolvedValue({ data: [], error: undefined });
});

describe('getMediaFiles', () => {
	it('fetches each media type at most once within a session', async () => {
		await getMediaFiles('image');
		await getMediaFiles('image');
		expect(imageGetAll).toHaveBeenCalledTimes(1);
	});

	it('returns undefined for an unknown media type', () => {
		expect(getMediaFiles('bogus')).toBeUndefined();
	});

	it('does not cache a failed load, so the next call retries', async () => {
		imageGetAll.mockRejectedValueOnce(new Error('boom'));
		await expect(getMediaFiles('image')).rejects.toThrow('boom');
		await getMediaFiles('image');
		expect(imageGetAll).toHaveBeenCalledTimes(2);
	});
});

describe('refreshMediaFiles', () => {
	it('invalidates one type so the next access re-fetches (the delete fix)', async () => {
		await getMediaFiles('image');
		refreshMediaFiles('image');
		await getMediaFiles('image');
		expect(imageGetAll).toHaveBeenCalledTimes(2);
	});

	it('only invalidates the named type, leaving others cached', async () => {
		await getMediaFiles('image');
		await getMediaFiles('comic');
		refreshMediaFiles('image');
		await getMediaFiles('image');
		await getMediaFiles('comic');
		expect(imageGetAll).toHaveBeenCalledTimes(2);
		expect(comicGetAll).toHaveBeenCalledTimes(1);
	});

	it('clears every type when called without an argument', async () => {
		await getMediaFiles('image');
		await getMediaFiles('comic');
		refreshMediaFiles();
		await getMediaFiles('image');
		await getMediaFiles('comic');
		expect(imageGetAll).toHaveBeenCalledTimes(2);
		expect(comicGetAll).toHaveBeenCalledTimes(2);
	});
});
