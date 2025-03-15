import {
	ComicComparison,
	MediaFileComparison,
	MediaType,
	VideoComparison,
	type MediaFileComparisonType
} from '$lib/model.svelte';

const basicOptions = [
	{ value: MediaFileComparison.Name, text: 'Name' },
	{ value: MediaFileComparison.Size, text: 'Size' },
	{ value: MediaFileComparison.UpdatedDate, text: 'Date' },
	{ value: MediaFileComparison.Path, text: 'Path' },
	{ value: MediaFileComparison.Id, text: 'ID' },
	{ value: MediaFileComparison.Random, text: 'Random' },
	{ value: MediaFileComparison.ViewedDate, text: 'ViewDate' }
];

const comicOptions = [
	{ value: ComicComparison.Page, text: 'Page' },
	{ value: ComicComparison.SizePerPage, text: 'SizePerPage' }
];

const videoOptions = [
	{ value: VideoComparison.Duration, text: 'Duration' },
	{ value: VideoComparison.SizePerSecond, text: 'SizePerSecond' }
];

export function getOrderByOptions(
	mediaType: MediaType
): { value: MediaFileComparisonType; text: string }[] {
	switch (mediaType) {
		case MediaType.Comic:
			return [...basicOptions, ...comicOptions];
		case MediaType.Video:
			return [...basicOptions, ...videoOptions];
		default:
			return basicOptions;
	}
}
