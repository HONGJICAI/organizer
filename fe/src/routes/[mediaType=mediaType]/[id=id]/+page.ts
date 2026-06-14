import { ComicsService, ImagesService, VideosService } from '$lib/client/sdk.gen';
import { Comic, Image, Video, type MediaFile } from '$lib/model.svelte';

interface Loaders {
	[key: string]: (id: number) => Promise<MediaFile | undefined>;
}

async function loadComic(id: number) {
	const { data } = await ComicsService.comicGet({ path: { id } });
	return data ? new Comic(data) : undefined;
}
async function loadVideo(id: number) {
	const { data } = await VideosService.videoGet({ path: { id } });
	return data ? new Video(data) : undefined;
}
async function loadImage(id: number) {
	const { data } = await ImagesService.imageGet({ path: { id } });
	return data ? new Image(data) : undefined;
}

const loaders: Loaders = {
	comic: loadComic,
	video: loadVideo,
	image: loadImage
};

export async function load({ params }) {
	const loader = loaders[params.mediaType];
	if (!loader) return { file: undefined };
	const file = await loader(Number(params.id));
	return { file };
}
