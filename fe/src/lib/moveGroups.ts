import { folderName, hasTag } from '$lib/moveTarget';
import type { TagIndex } from '$lib/tagIndex';
import { separateFilename } from '$lib/utility';

// Rows of the Move to folder table: every author tag (Tags -> Classify), plus
// one for any other tag being looked at, each with its comics and whether
// they already sit in a folder named after it.

interface FileLike {
	id: number;
	name: string;
	path: string;
	archived: boolean;
}

export interface GroupComic {
	id: number;
	name: string;
	path: string;
	/** The folder holding the comic. */
	folder: string;
	/** Already in a folder named after the group. */
	inPlace: boolean;
	/** Other authors of the comic: left out by default, the user picks one. */
	otherAuthors: string[];
}

export interface MoveGroup {
	/** The primary tag; the folder is named after it. */
	key: string;
	isAuthor: boolean;
	/** The tag and its aliases. */
	names: string[];
	comics: GroupComic[];
	/** Comics moved by default: not in place, single author. */
	pending: number[];
}

function splitFolder(path: string): [string, string] {
	const i = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
	const folder = i > 0 ? path.slice(0, i) : '';
	const j = Math.max(folder.lastIndexOf('/'), folder.lastIndexOf('\\'));
	return [folder, folder.slice(j + 1)];
}

// Folder names that are the same folder on a case-insensitive or normalizing
// filesystem (NTFS, SMB, macOS), as the backend compares them.
const sameName = (a: string, b: string) =>
	a.normalize('NFC').toLowerCase() === b.normalize('NFC').toLowerCase();

function makeGroup(key: string, isAuthor: boolean, names: string[]): MoveGroup {
	return { key, isAuthor, names, comics: [], pending: [] };
}

function addComic(group: MoveGroup, f: FileLike, otherAuthors: string[]) {
	const [folder, parentName] = splitFolder(f.path);
	const inPlace = sameName(parentName, folderName(group.key));
	group.comics.push({ id: f.id, name: f.name, path: f.path, folder, inPlace, otherAuthors });
	if (!inPlace && !otherAuthors.length) group.pending.push(f.id);
}

/** Groups with work first (most pending), then by name. */
export function sortGroups(groups: MoveGroup[]): MoveGroup[] {
	return groups.sort(
		(a, b) =>
			Number(!a.pending.length) - Number(!b.pending.length) ||
			b.pending.length - a.pending.length ||
			a.key.localeCompare(b.key)
	);
}

export function authorGroups(files: FileLike[], index: TagIndex): MoveGroup[] {
	const groups = new Map<string, MoveGroup>();
	for (const f of files) {
		if (f.archived) continue;
		const authors = [
			...new Set(
				separateFilename(f.name)
					.filter((t) => index.kind(t) === 'author')
					.map((t) => index.canonical(t))
			)
		];
		for (const author of authors) {
			let group = groups.get(author);
			if (!group) {
				group = makeGroup(author, true, index.names(author));
				groups.set(author, group);
			}
			addComic(
				group,
				f,
				authors.filter((a) => a !== author)
			);
		}
	}
	return sortGroups([...groups.values()]);
}

/** A row for any tag (and its aliases); null when no comic has it. */
export function tagGroup(files: FileLike[], index: TagIndex, tag: string): MoveGroup | null {
	const key = index.canonical(tag.trim());
	if (!key) return null;
	const group = makeGroup(key, index.kind(key) === 'author', index.names(key));
	for (const f of files) {
		if (!f.archived && hasTag(f.name, group.names)) addComic(group, f, []);
	}
	return group.comics.length ? group : null;
}
