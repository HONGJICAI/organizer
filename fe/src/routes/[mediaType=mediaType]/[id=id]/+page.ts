import { config } from '$lib/config.svelte';
import { Comic, Image, Video } from '$lib/model.svelte';
interface Map {
	[key: string]: (id: string) => Promise<Comic | Video | Image>;
}
const mediaTypes: Map = {
	comic: loadComic,
	video: loadVideo,
	image: loadImage
};

async function loadComic(id: string) {
	const rsp = await fetch(`${config.apiServer}/api/comics/${id}`);
	const json = await rsp.json();
	return new Comic(json);
}
async function loadVideo(id: string) {
	const rsp = await fetch(`${config.apiServer}/api/videos/${id}`);
	const json = await rsp.json();
	return new Video(json);
}
async function loadImage(id: string) {
	const rsp = await fetch(`${config.apiServer}/api/images/${id}`);
	const json = await rsp.json();
	return new Image(json);
}
export async function load({ params }) {
	const p = mediaTypes[params.mediaType];
	if (!p) return { file: undefined };
	const file = await p(params.id);
	return { file };
}
