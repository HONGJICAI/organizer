import { config } from '$lib/config.svelte';
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
	const rsp = await fetch(`${config.apiServer}/api/comics`);
	const json = await rsp.json();
	return json.map((e: any) => new Comic(e));
}
async function loadVideos(): Promise<Video[]> {
	const rsp = await fetch(`${config.apiServer}/api/videos`);
	const json = await rsp.json();
	return json.map((e: any) => new Video(e));
}
async function loadImages(): Promise<MediaFile[]> {
	const rsp = await fetch(`${config.apiServer}/api/images`);
	const json = await rsp.json();
	return json.map((e: any) => new MediaFile(MediaType.Image, e));
}
export async function load({ params }) {
	const p = mediaTypes[params.mediaType];
	if (!p) {
		return {
			status: 404
		};
	}

	return {
		files: p(),
	};
}
