import { separateFilename } from '$lib/utility';

// Helpers for the "move a tag's comics into one folder" page.

// Comics whose name carries `tag` as a whole tag (the same split as the tag
// page), unlike the list search, which matches any substring.
export function hasTag(name: string, tag: string): boolean {
	const t = tag.trim();
	return t !== '' && separateFilename(name).includes(t);
}
