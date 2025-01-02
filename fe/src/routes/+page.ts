import { redirect } from '@sveltejs/kit';

export async function load({ params }) {
	redirect(304, '/comic');
}
