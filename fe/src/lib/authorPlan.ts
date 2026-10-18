import { folderName } from '$lib/moveTarget';
import type { TagIndex } from '$lib/tagIndex';
import { separateFilename } from '$lib/utility';

// "Gather every author": which comics belong to which author (aliases
// included) and which of them aren't in a folder named after the author yet.

interface FileLike {
	id: number;
	name: string;
	path: string;
	archived: boolean;
}

export interface AuthorPlan {
	author: string;
	/** Every live comic of the author. */
	ids: number[];
	/** Those not in a folder named after the author. */
	outside: number[];
}

export interface AuthorPlans {
	authors: AuthorPlan[];
	/** Comics with more than one author: left out, the user decides per author. */
	multi: { id: number; name: string; authors: string[] }[];
}

function parentName(path: string): string {
	const parts = path.split(/[/\\]+/).filter(Boolean);
	return parts.length > 1 ? parts[parts.length - 2] : '';
}

export function planAuthors(files: FileLike[], index: TagIndex): AuthorPlans {
	const byAuthor = new Map<string, AuthorPlan>();
	const multi: AuthorPlans['multi'] = [];
	for (const f of files) {
		if (f.archived) continue;
		const authors = [
			...new Set(
				separateFilename(f.name)
					.filter((t) => index.kind(t) === 'author')
					.map((t) => index.canonical(t))
			)
		];
		if (authors.length > 1) {
			multi.push({ id: f.id, name: f.name, authors });
			continue;
		}
		const [author] = authors;
		if (!author) continue;
		const plan = byAuthor.get(author) ?? { author, ids: [], outside: [] };
		plan.ids.push(f.id);
		if (parentName(f.path) !== folderName(author)) plan.outside.push(f.id);
		byAuthor.set(author, plan);
	}
	const authors = [...byAuthor.values()].sort(
		(a, b) => b.outside.length - a.outside.length || a.author.localeCompare(b.author)
	);
	return { authors, multi };
}
