import type { HomeResponse, HomeSection } from '$lib/client';
import { Comic, Image, Video, type MediaFile } from '$lib/model.svelte';

// The home feed (GET /api/home) returns each section split by media type; the
// page shows one row per section mixing the types.

export const ROW_SIZE = 12;

export type HomeRows = {
	continueReading: MediaFile[];
	recent: MediaFile[];
	favorites: MediaFile[];
	random: MediaFile[];
};

function byType(section: HomeSection): MediaFile[][] {
	return [
		(section.comics ?? []).map((e) => new Comic(e)),
		(section.videos ?? []).map((e) => new Video(e)),
		(section.images ?? []).map((e) => new Image(e))
	];
}

// Newest `key` first across all types.
function merged(section: HomeSection, key: (f: MediaFile) => number): MediaFile[] {
	return byType(section)
		.flat()
		.sort((a, b) => key(b) - key(a))
		.slice(0, ROW_SIZE);
}

// Take from each type in turn, so a big comic library doesn't crowd out the
// rest of a random pick.
export function interleave<T>(lists: T[][]): T[] {
	const out: T[] = [];
	for (let i = 0; out.length < ROW_SIZE && lists.some((l) => i < l.length); i++) {
		for (const list of lists) if (i < list.length && out.length < ROW_SIZE) out.push(list[i]);
	}
	return out;
}

export function randomRow(section: HomeSection): MediaFile[] {
	return interleave(byType(section));
}

export function homeRows(data: HomeResponse): HomeRows {
	return {
		continueReading: merged(data.continueReading, (f) => f.lastViewedDate?.getTime() ?? 0),
		recent: merged(data.recent, (f) => f.updateDate.getTime()),
		favorites: merged(data.favorites, (f) => f.updateDate.getTime()),
		random: randomRow(data.random)
	};
}

// Where a card opens: the reader, at the last-read page when resuming.
export function readerUrl(file: MediaFile, resume = false): string {
	const url = `/${file.type}/${file.id}`;
	return resume && file.lastViewed > 1 ? `${url}?page=${file.lastViewed}` : url;
}
