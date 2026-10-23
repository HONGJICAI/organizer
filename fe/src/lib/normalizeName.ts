// Name normalization for Cleanup → Normalize: full-width letters, digits and
// round/square/curly brackets to half-width, tidy spaces, and language tags moved to the end. Each rule
// is separate so the page can turn them off one by one and say which changed
// a name.

import { checkName, splitExtension } from '$lib/nameCheck';

export type NormalizeRule = 'width' | 'brackets' | 'kana' | 'spaces' | 'language';

export const ruleLabels: Record<NormalizeRule, string> = {
	width: 'Full-width letters and digits',
	brackets: 'Full-width brackets',
	kana: 'Half-width katakana',
	spaces: 'Spaces',
	language: 'Language last'
};
export const rules = Object.keys(ruleLabels) as NormalizeRule[];

// Full-width symbols are left alone. Japanese titles use ！？～ on purpose,
// and ？：＊＂＜＞｜／＼ usually stand in for characters Windows (NTFS, SMB)
// doesn't allow in file names: narrowed, the rename would fail or the name
// would become a path. Only （）［］｛｝ are narrowed, so they read as tags;
// 【】 and 《》 have no half-width form and are read as they are.
const pairs = new Map([
	['(', ')'],
	['[', ']'],
	['{', '}'],
	['【', '】'],
	['<', '>'],
	['《', '》']
]);

const narrowChar = (c: string) => String.fromCharCode(c.charCodeAt(0) - 0xfee0);

/** Full-width letters and digits (Ａ, ｚ, １) and the ideographic space to half-width. */
export function narrowWidth(s: string): string {
	return s.replace(/[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a\u3000]/g, (c) =>
		c === '\u3000' ? ' ' : narrowChar(c)
	);
}

function narrowBrackets(s: string): string {
	return s.replace(/[（）［］｛｝]/g, narrowChar);
}

// NFKC on half-width katakana only, so ｶﾞ becomes ガ (one character).
function widenKana(s: string): string {
	return s.replace(/[\uff61-\uff9f]+/g, (run) => run.normalize('NFKC'));
}

function tidySpaces(s: string): string {
	return s.replace(/\s+/g, ' ').trim();
}

/**
 * Bracketed tags whose text is a language moved to the end, in their order.
 * Left alone when the brackets don't pair up: then what's a tag isn't clear.
 */
function languageLast(s: string, isLanguage: (tag: string) => boolean): string {
	if (checkName(s).some((p) => p.kind !== 'untagged' && p.kind !== 'empty')) return s;
	const rest: string[] = [];
	const moved: string[] = [];
	let last = 0;
	for (let i = 0; i < s.length; i++) {
		const close = pairs.get(s[i]);
		if (close === undefined) continue;
		const j = s.indexOf(close, i + 1);
		if (isLanguage(s.slice(i + 1, j).trim())) {
			rest.push(s.slice(last, i));
			moved.push(s.slice(i, j + 1));
			last = j + 1;
		}
		i = j;
	}
	if (!moved.length) return s;
	rest.push(s.slice(last));
	return tidySpaces([...rest, ' ', ...moved.map((m) => ` ${m}`)].join(''));
}

export interface Normalized {
	name: string;
	/** The rules that changed something, in the order they ran. */
	changed: NormalizeRule[];
}

/**
 * ``name`` normalized by the rules in ``use``; the archive extension is kept.
 * ``isLanguage`` gets a tag's text after the width rules ran.
 */
export function normalizeName(
	name: string,
	use: ReadonlySet<NormalizeRule>,
	isLanguage: (tag: string) => boolean
): Normalized {
	const [stem, ext] = splitExtension(name);
	const steps: [NormalizeRule, (s: string) => string][] = [
		['width', narrowWidth],
		['brackets', narrowBrackets],
		['kana', widenKana],
		['spaces', tidySpaces],
		['language', (s) => languageLast(s, isLanguage)]
	];
	let s = stem;
	const changed: NormalizeRule[] = [];
	for (const [rule, step] of steps) {
		if (!use.has(rule)) continue;
		const next = step(s);
		if (next !== s) changed.push(rule);
		s = next;
	}
	return { name: s + ext, changed };
}
