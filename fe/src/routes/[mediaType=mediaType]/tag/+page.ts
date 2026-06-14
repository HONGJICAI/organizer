import { getMediaFiles } from '$lib/mediaStore';

export function load({ params, depends }) {
	depends(`app:media:${params.mediaType}`);
	const files = getMediaFiles(params.mediaType);
	if (!files) {
		return {
			status: 404
		};
	}
	return {
		mediaType: params.mediaType,
		files
	};
}
