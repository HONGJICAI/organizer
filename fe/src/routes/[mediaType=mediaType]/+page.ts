import { getMediaFiles } from '$lib/mediaStore';

export function load({ params, depends }) {
	// Scopes the refresh button: invalidate(`app:media:<type>`) re-runs only this
	// load, not every load in the app.
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
