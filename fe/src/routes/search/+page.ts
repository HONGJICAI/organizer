import { ComicsService, ImagesService, VideosService } from '$lib/client/sdk.gen.js';
import { Comic, Image, Video, type MediaFile } from '$lib/model.svelte';

// Global search loads every media type and filters client-side, mirroring the
// per-type list pages (which already load their whole list and filter in the
// browser). A failure in one type must not blank the others, so each loader
// resolves to [] on error.
async function loadComics(): Promise<MediaFile[]> {
	const { data, error } = await ComicsService.comicGetAll();
	if (error || !data) {
		return [];
	}
	return data.map((e) => new Comic(e));
}
async function loadVideos(): Promise<MediaFile[]> {
	const { data, error } = await VideosService.videoGetAll();
	if (error || !data) {
		return [];
	}
	return data.map((e) => new Video(e));
}
async function loadImages(): Promise<MediaFile[]> {
	const { data, error } = await ImagesService.imageGetAll();
	if (error || !data) {
		return [];
	}
	return data.map((e) => new Image(e));
}

export function load() {
	return {
		comics: loadComics(),
		videos: loadVideos(),
		images: loadImages()
	};
}
