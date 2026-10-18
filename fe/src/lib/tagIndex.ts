import type { TagInfo } from '$lib/client';
import { separateFilename } from '$lib/utility';

// What the user decided about file-name tags (api/tags.py): a kind, and
// aliases pointing at a primary tag. Tags without a row are unclassified.

export type TagKind = 'author' | 'circle' | 'language' | 'ignored';
export const tagKinds: TagKind[] = ['author', 'circle', 'language', 'ignored'];
export const kindLabel: Record<TagKind, string> = {
	author: 'Author',
	circle: 'Circle',
	language: 'Language',
	ignored: 'Ignored'
};
// Carbon Tag colors per kind; unclassified tags stay teal as before.
export const kindColor: Record<TagKind | 'none', 'purple' | 'magenta' | 'cyan' | 'gray' | 'teal'> =
	{
		author: 'purple',
		circle: 'magenta',
		language: 'cyan',
		ignored: 'gray',
		none: 'teal'
	};

export class TagIndex {
	private rows = new Map<string, TagInfo>();
	private lower = new Map<string, string>();
	private aliases = new Map<string, string[]>();

	constructor(rows: TagInfo[] = []) {
		for (const row of rows) {
			this.rows.set(row.name, row);
			this.lower.set(row.name.toLowerCase(), row.name);
			if (row.canonical) {
				const list = this.aliases.get(row.canonical) ?? [];
				list.push(row.name);
				this.aliases.set(row.canonical, list);
			}
		}
	}

	get size(): number {
		return this.rows.size;
	}

	row(name: string): TagInfo | undefined {
		return this.rows.get(name);
	}

	/** The primary tag `name` stands for: its canonical tag, or itself. */
	canonical(name: string): string {
		return this.rows.get(name)?.canonical ?? name;
	}

	/** The kind of `name`, taken from its primary tag. */
	kind(name: string): TagKind | undefined {
		return (this.rows.get(this.canonical(name))?.kind ?? undefined) as TagKind | undefined;
	}

	/** Every name of the tag `name` belongs to: the primary first, then its aliases. */
	names(name: string): string[] {
		const primary = this.canonical(name);
		return [primary, ...(this.aliases.get(primary) ?? [])];
	}

	/** Like names(), looked up case-insensitively (search keywords are lower case). */
	namesIgnoringCase(keyword: string): string[] {
		const name = this.lower.get(keyword.toLowerCase());
		return name === undefined ? [keyword] : this.names(name);
	}
}

/** Primary tags of a tag source (file name or path), without ignored ones. */
export function primaryTags(source: string, index: TagIndex): string[] {
	const tags = new Set<string>();
	for (const tag of separateFilename(source)) {
		const primary = index.canonical(tag);
		if (index.kind(primary) !== 'ignored') tags.add(primary);
	}
	return [...tags];
}

/** Files per primary tag; a file with both a tag and its alias counts once. */
export function countTags(sources: string[], index: TagIndex): Map<string, number> {
	const counts = new Map<string, number>();
	for (const source of sources) {
		for (const tag of primaryTags(source, index)) counts.set(tag, (counts.get(tag) ?? 0) + 1);
	}
	return counts;
}

export interface TagGroups {
	author: Map<string, number>;
	circle: Map<string, number>;
	language: Map<string, number>;
	other: Map<string, number>;
}

export function groupTags(counts: Map<string, number>, index: TagIndex): TagGroups {
	const groups: TagGroups = {
		author: new Map(),
		circle: new Map(),
		language: new Map(),
		other: new Map()
	};
	for (const [tag, n] of counts) {
		const kind = index.kind(tag);
		if (kind === 'ignored') continue;
		groups[kind ?? 'other'].set(tag, n);
	}
	return groups;
}

/**
 * The list search: every keyword must appear in `source`; a keyword that is a
 * classified tag also matches through its aliases. Both sides lower case.
 */
export function matchesKeywords(source: string, keywords: string[], index: TagIndex): boolean {
	return keywords.every((k) =>
		index.namesIgnoringCase(k).some((name) => source.includes(name.toLowerCase()))
	);
}
