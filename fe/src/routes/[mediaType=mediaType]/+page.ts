import { getMediaFiles } from '$lib/mediaStore';

export function load({ params }) {
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
