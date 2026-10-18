import { separateFilename } from '$lib/utility';

// Helpers for the "move a tag's comics into one folder" page.

// Comics whose name carries `tag` as a whole tag (the same split as the tag
// page), unlike the list search, which matches any substring.
export function hasTag(name: string, tag: string): boolean {
	const t = tag.trim();
	return t !== '' && separateFilename(name).includes(t);
}

// A folder name from a tag: path separators and characters Windows/SMB shares
// reject become `_`, and trailing dots/spaces (also rejected there) are dropped.
export function folderName(tag: string): string {
	return tag
		.trim()
		.replace(/[/\\:*?"<>|]/g, '_')
		.replace(/[. ]+$/, '');
}

function splitDir(path: string): [string, string] {
	const i = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
	return i < 0 ? ['', path] : [path.slice(0, i), path.slice(i + 1)];
}

// Suggested target: next to where most of the comics already are, i.e.
// `<their most common folder>/<tag>`, or that folder itself when it is
// already named after the tag. Staying beside the comics keeps the move on the
// same drive (a rename) in the usual case. '' when there's nothing to go on.
export function defaultTarget(paths: string[], tag: string): string {
	const name = folderName(tag);
	if (!paths.length || !name) return '';
	const counts = new Map<string, number>();
	for (const p of paths) {
		const [dir] = splitDir(p);
		counts.set(dir, (counts.get(dir) ?? 0) + 1);
	}
	let best = '';
	let bestCount = 0;
	for (const [dir, n] of counts) {
		if (n > bestCount) [best, bestCount] = [dir, n];
	}
	if (splitDir(best)[1] === name) return best;
	const sep = best.includes('\\') && !best.includes('/') ? '\\' : '/';
	return `${best}${sep}${name}`;
}
