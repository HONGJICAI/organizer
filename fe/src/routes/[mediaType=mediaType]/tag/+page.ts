import { ComicsService, ImagesService, VideosService } from '$lib/client/sdk.gen.js';
import { Comic, MediaFile, MediaType, Video } from '$lib/model.svelte';
interface Map {
	[key: string]: () => Promise<Comic[] | Video[] | MediaFile[]>;
}
const mediaTypes: Map = {
	comic: loadComics,
	video: loadVideos,
	image: loadImages
};
async function loadComics(): Promise<Comic[]> {
	const { data, error } = await ComicsService.comicGetAll();
	if (error) {
		throw error;
	}
	return data.map((e) => new Comic(e));
}
async function loadVideos(): Promise<Video[]> {
	const { data, error } = await VideosService.videoGetAll();
	if (error) {
		throw error;
	}
	return data.map((e) => new Video(e));
}
async function loadImages(): Promise<MediaFile[]> {
	const { data, error } = await ImagesService.imageGetAll();
	if (error) {
		throw error;
	}
	return data.map((e) => new MediaFile(MediaType.Image, e));
}
export async function load({ params }) {
	const p = mediaTypes[params.mediaType];
	if (!p) {
		return {
			status: 404
		};
	}
	return {
		mediaType: params.mediaType,
		files: p()
	};
}
