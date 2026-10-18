import { separateFilename } from '$lib/utility';

// Helpers for the "move a tag's comics into one folder" page.

// Comics whose name carries `tag` (or any of several names, e.g. an author
// and its aliases) as a whole tag, the same split as the tag page; the list
// search instead matches any substring.
export function hasTag(name: string, tag: string | string[]): boolean {
	const wanted = new Set((Array.isArray(tag) ? tag : [tag]).map((t) => t.trim()).filter(Boolean));
	return wanted.size > 0 && separateFilename(name).some((t) => wanted.has(t));
}

// A folder name from a tag, as mover.folder_name makes it: path separators
// and characters Windows/SMB shares reject become `_`, trailing dots and
// spaces are dropped.
export function folderName(tag: string): string {
	return (
		tag
			.trim()
			// eslint-disable-next-line no-control-regex -- control characters are what's replaced
			.replace(/[/\\:*?"<>|\u0000-\u001f]/g, '_')
			.replace(/[. ]+$/, '')
	);
}
