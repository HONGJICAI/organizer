import { TagsService } from '$lib/client';
import { errorMessage } from '$lib/mediaAdapters';
import { TagIndex, type TagKind } from '$lib/tagIndex';

// Session-wide tag classification, loaded once and replaced after each change
// (the API returns every classified tag, so there's nothing to merge).
export const tagState = $state({ index: new TagIndex(), loaded: false });

let pending: Promise<void> | null = null;

export function loadTags(): Promise<void> {
	pending ??= TagsService.tagGetAll().then(({ data, error }) => {
		if (error !== undefined || !data) {
			// Retry on the next call rather than caching the failure.
			pending = null;
		} else {
			tagState.index = new TagIndex(data);
		}
		tagState.loaded = true;
	});
	return pending;
}

/** Give `names` a kind, or unclassify them with null. Resolves to an error message. */
export async function setTagKind(
	names: string[],
	kind: TagKind | null
): Promise<string | undefined> {
	const { data, error } = await TagsService.tagSetKind({ body: { names, kind } });
	if (error !== undefined || !data) return errorMessage(error);
	tagState.index = new TagIndex(data.tags);
}

/** Make `aliases` aliases of `primary`. Resolves to an error message. */
export async function mergeTags(primary: string, aliases: string[]): Promise<string | undefined> {
	const { data, error } = await TagsService.tagMerge({ body: { primary, aliases } });
	if (error !== undefined || !data) return errorMessage(error);
	tagState.index = new TagIndex(data.tags);
}
