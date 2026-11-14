// Keyboard shortcuts, dispatched from one window listener.
//
// The reader opens on top of the list page (shallow routing), and the page
// overview on top of the reader, so several components are mounted at once.
// Each registers its keys in a layer; a key press goes only to the highest
// layer that has any keys registered. Within that layer the most recently
// registered scope that binds the key wins. Lower layers never see it, so the
// reader doesn't turn pages behind the open overview.

export enum Layer {
	Page = 0,
	Reader = 10,
	Overlay = 20
}

export interface Hotkey {
	// KeyboardEvent.key values, e.g. 'ArrowLeft', 'Escape', 'o', '+'.
	keys: string[];
	// What it does, for a shortcut list.
	description: string;
	// Omitted for keys the focused element handles itself (Enter on a card or
	// button): listed in the shortcut help, never claimed here.
	run?: (e: KeyboardEvent) => void;
	// Fire on auto-repeat while held. Off by default: holding a key would
	// otherwise queue dozens of actions (e.g. close the reader, then the next
	// Escape lands on whatever is underneath).
	repeat?: boolean;
}

interface Scope {
	layer: Layer;
	hotkeys: Hotkey[];
}

const scopes: Scope[] = [];

// Typing in a field keeps its own keys: arrows move the caret, digits go into
// the page number box.
function isEditable(target: EventTarget | null): boolean {
	const el = target as HTMLElement | null;
	if (!el || typeof el.tagName !== 'string') return false;
	if (el.isContentEditable) return true;
	const tag = el.tagName;
	if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
	if (tag !== 'INPUT') return false;
	const type = (el as HTMLInputElement).type;
	return !['button', 'checkbox', 'radio', 'range', 'reset', 'submit'].includes(type);
}

// A Carbon modal (settings, file details, confirmations) owns the keyboard
// while it is open; it handles Escape itself.
function modalOpen(): boolean {
	return (
		typeof document !== 'undefined' && document.querySelector('.bx--modal.is-visible') !== null
	);
}

export function dispatch(e: KeyboardEvent): boolean {
	if (e.defaultPrevented || e.isComposing) return false;
	// Ctrl/Cmd/Alt combinations stay the browser's (Alt+← is Back, Ctrl+= is
	// zoom). Shift is allowed: '+' and '?' need it on most layouts.
	if (e.ctrlKey || e.metaKey || e.altKey) return false;
	if (isEditable(e.target) || modalOpen()) return false;
	if (scopes.length === 0) return false;
	if (e.key === '?' && helpHandler) {
		e.preventDefault();
		if (!e.repeat) helpHandler();
		return true;
	}
	const top = Math.max(...scopes.map((s) => s.layer));
	for (let i = scopes.length - 1; i >= 0; i--) {
		const scope = scopes[i];
		if (scope.layer !== top) continue;
		const hotkey = scope.hotkeys.find((h) => h.run && h.keys.includes(e.key));
		if (!hotkey?.run) continue;
		e.preventDefault();
		if (!e.repeat || hotkey.repeat) hotkey.run(e);
		return true;
	}
	return false;
}

function onKeydown(e: KeyboardEvent) {
	dispatch(e);
}

// Registers a component's shortcuts; call from onMount and return the result
// so they go away on unmount. The window listener lives only while some scope
// is registered.
export function registerHotkeys(layer: Layer, hotkeys: Hotkey[]): () => void {
	const scope: Scope = { layer, hotkeys };
	if (scopes.length === 0 && typeof window !== 'undefined')
		window.addEventListener('keydown', onKeydown);
	scopes.push(scope);
	return () => {
		const i = scopes.indexOf(scope);
		if (i === -1) return;
		scopes.splice(i, 1);
		if (scopes.length === 0 && typeof window !== 'undefined')
			window.removeEventListener('keydown', onKeydown);
	};
}

// '?' shows the shortcut list, wherever shortcuts are registered. The layout
// sets the handler that opens it.
let helpHandler: (() => void) | null = null;

export function setHotkeyHelp(handler: (() => void) | null) {
	helpHandler = handler;
}

// The shortcuts that currently react (the top layer's, latest scope first),
// for the help list. A key listed twice keeps its first description.
export function activeHotkeys(): Hotkey[] {
	if (scopes.length === 0) return [];
	const top = Math.max(...scopes.map((s) => s.layer));
	const seen = new Set<string>();
	const list: Hotkey[] = [];
	for (const scope of scopes.filter((s) => s.layer === top).reverse()) {
		for (const hotkey of scope.hotkeys) {
			const keys = hotkey.keys.filter((k) => !seen.has(k));
			if (keys.length === 0) continue;
			keys.forEach((k) => seen.add(k));
			list.push({ ...hotkey, keys });
		}
	}
	return list;
}

const KEY_LABELS: Record<string, string> = {
	ArrowLeft: '←',
	ArrowRight: '→',
	ArrowUp: '↑',
	ArrowDown: '↓',
	Escape: 'Esc',
	PageUp: 'PgUp',
	PageDown: 'PgDn',
	' ': 'Space'
};

/** How a KeyboardEvent.key value is shown in the shortcut list. */
export function keyLabel(key: string): string {
	return KEY_LABELS[key] ?? key;
}
