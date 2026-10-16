import { HomeService } from '$lib/client/sdk.gen.js';

export function load() {
	return { home: HomeService.homeGet() };
}
