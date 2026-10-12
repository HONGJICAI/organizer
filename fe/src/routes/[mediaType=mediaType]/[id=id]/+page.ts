import { adapterFor } from '$lib/mediaAdapters';

export async function load({ params }) {
	const adapter = adapterFor(params.mediaType);
	if (!adapter) return { file: undefined };
	const { data } = await adapter.get(Number(params.id));
	return { file: data };
}
