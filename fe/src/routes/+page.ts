import { ComicsService, ImagesService, VideosService } from '$lib/client/sdk.gen.js';

export async function load() {
	return {
		comics: ComicsService.comicGetAll({
			query: {
				top: 8
			}
		}),
		videos: VideosService.videoGetAll({
			query: {
				top: 8
			}
		}),
		images: ImagesService.imageGetAll({
			query: {
				top: 8
			}
		})
	};
}
