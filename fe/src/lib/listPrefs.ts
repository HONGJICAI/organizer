// How a list is sorted and filtered, remembered for the tab's session so it
// survives a reload or a trip to another page. Each list keeps its own: comic,
// video and image lists offer different sort keys, and a folder page sorts by
// name by default where the media list sorts by date.

export interface ListPrefs {
	orderBy: number;
	reverse: boolean;
	unreadOnly: boolean;
	includeSub: boolean;
}

const KEY_PREFIX = 'organizer.list.';

/** The saved prefs for `list`, each falling back to its default when missing or malformed. */
export function loadListPrefs(list: string, defaults: ListPrefs): ListPrefs {
	let saved: Record<string, unknown> = {};
	try {
		const parsed: unknown = JSON.parse(sessionStorage.getItem(KEY_PREFIX + list) ?? '{}');
		if (parsed && typeof parsed === 'object') saved = parsed as Record<string, unknown>;
	} catch {
		// Storage blocked or bad JSON: defaults.
	}
	const bool = (v: unknown, d: boolean) => (typeof v === 'boolean' ? v : d);
	return {
		orderBy: Number.isInteger(saved.orderBy) ? (saved.orderBy as number) : defaults.orderBy,
		reverse: bool(saved.reverse, defaults.reverse),
		unreadOnly: bool(saved.unreadOnly, defaults.unreadOnly),
		includeSub: bool(saved.includeSub, defaults.includeSub)
	};
}

export function saveListPrefs(list: string, prefs: ListPrefs) {
	try {
		sessionStorage.setItem(KEY_PREFIX + list, JSON.stringify(prefs));
	} catch {
		// Storage unavailable: the choice holds until the page is left.
	}
}

/**
 * The sort key to use: the chosen one when the list offers it, else the
 * list's first. Recent and Archive only sort by view date; the chosen key is
 * kept for when the list offers it again.
 */
export function effectiveOrderBy<T extends number>(chosen: number, options: { value: T }[]): T {
	const match = options.find((o) => o.value === chosen);
	return (match ?? options[0])?.value ?? (chosen as T);
}
