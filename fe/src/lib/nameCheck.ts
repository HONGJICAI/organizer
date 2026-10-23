// Finds comic names that the tag splitter (separateFilename in utility.ts)
// reads wrong. It takes each opening bracket up to the first closing bracket of
// the same type, so a bracket left open drops every tag of the name, a nested
// one cuts its tag short, and a stray closer ends up inside a tag.

const pairs = new Map<string, string>([
	['(', ')'],
	['[', ']'],
	['{', '}'],
	['【', '】'],
	['<', '>'],
	['《', '》']
]);
const closers = new Map([...pairs].map(([open, close]) => [close, open]));

export type NameProblemKind = 'unclosed' | 'nested' | 'stray' | 'empty' | 'untagged';

export interface NameProblem {
	kind: NameProblemKind;
	/** Where in the name, or -1 for the whole name. */
	at: number;
	message: string;
}

export const problemLabels: Record<NameProblemKind, string> = {
	unclosed: 'Unclosed bracket',
	nested: 'Nested bracket',
	stray: 'Stray closing bracket',
	empty: 'Empty brackets',
	untagged: 'No tags'
};

/** Problems in the order they appear; none for a well-formed name. */
export function checkName(name: string): NameProblem[] {
	const problems: NameProblem[] = [];
	let tagged = false;
	for (let i = 0; i < name.length; i++) {
		const c = name[i];
		const close = pairs.get(c);
		if (close !== undefined) {
			tagged = true;
			const j = name.indexOf(close, i + 1);
			if (j < 0) {
				// Name the closer that follows instead, if any: usually a typo.
				const other = [...name.slice(i + 1)].find((d) => closers.has(d));
				problems.push({
					kind: 'unclosed',
					at: i,
					message:
						`“${c}” is never closed by “${close}”` +
						(other ? ` (closed with “${other}” instead?)` : '') +
						'; the name loses all its tags'
				});
				return problems;
			}
			const inner = name.slice(i + 1, j);
			const reopened = inner.indexOf(c);
			if (reopened >= 0) {
				problems.push({
					kind: 'nested',
					at: i + 1 + reopened,
					message: `“${c}” inside “${c}…${close}”: the tag ends at the first “${close}”`
				});
			} else if (!inner.trim()) {
				problems.push({ kind: 'empty', at: i, message: `Empty “${c}${close}”` });
			}
			i = j;
		} else if (closers.has(c)) {
			problems.push({
				kind: 'stray',
				at: i,
				message: `“${c}” closes nothing; it stays in the tag text`
			});
		}
	}
	if (!tagged) {
		problems.push({ kind: 'untagged', at: -1, message: 'No bracketed tags (no author)' });
	}
	return problems;
}

const extension = /\.(zip|rar)$/i;

/** A comic name split into the part to edit and its archive extension. */
export function splitExtension(name: string): [string, string] {
	const m = name.match(extension);
	return m ? [name.slice(0, -m[0].length), m[0]] : [name, ''];
}
