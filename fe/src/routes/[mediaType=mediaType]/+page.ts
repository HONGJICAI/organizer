import { config } from '$lib/config';
import { Comic, MediaFile, MediaType, Video } from '$lib/model';

const mediaTypes = {
	comic: loadComics,
	video: loadVideos,
	image: loadImages,
};

async function loadComics() {
	try {
		const rsp = await fetch(`${config.apiServer}/api/comics`);
		const json = await rsp.json();
		return json.map((e: any) => new Comic(e));
	}
	catch (e) {
		console.error(e);
		return [];
	}
}
async function loadVideos() {
	const rsp = await fetch(`${config.apiServer}/api/videos`);
	const json = await rsp.json();
	return json.map((e: any) => new Video(e));
}
async function loadImages() {
	const rsp = await fetch(`${config.apiServer}/api/images`);
	const json = await rsp.json();
	return json.map((e: any) => new MediaFile(MediaType.Image, e));
}
export async function load({ params }) {
	const p = mediaTypes[params.mediaType];
	console.log(params.mediaType);
	if (!p) {
		return {
			status: 404
		};
	}

	const files = await p();
	return {
		files: files,
	};
}
