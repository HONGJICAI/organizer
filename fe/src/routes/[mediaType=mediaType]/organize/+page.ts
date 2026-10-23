import { redirect } from '@sveltejs/kit';

// The page was renamed to Cleanup; keep old links working.
export function load({ params }) {
	redirect(308, `/${params.mediaType}/cleanup`);
}
