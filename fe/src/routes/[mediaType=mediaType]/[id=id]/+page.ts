import { config } from '$lib/config';
import { Comic, Video } from '$lib/model.svelte';
interface Map {
	[key: string]: (id: string) => Promise<Comic | Video> | undefined
}
const mediaTypes: Map = {
	comic: loadComic,
	video: loadVideo
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
export async function load({ params }) {
	const p = mediaTypes[params.mediaType];
	const file = await p(params.id);
	return {
		file: file
	};
}
