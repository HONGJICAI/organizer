import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	activeHotkeys,
	dispatch,
	keyLabel,
	Layer,
	registerHotkeys,
	setHotkeyHelp
} from './hotkeys';

function key(k: string, init: Partial<KeyboardEvent> = {}) {
	const e = {
		key: k,
		repeat: false,
		ctrlKey: false,
		metaKey: false,
		altKey: false,
		shiftKey: false,
		isComposing: false,
		defaultPrevented: false,
		target: null,
		...init,
		preventDefault: vi.fn()
	};
	return e as unknown as KeyboardEvent & { preventDefault: ReturnType<typeof vi.fn> };
}

const cleanups: (() => void)[] = [];
function register(layer: Layer, keys: string[], opts: { repeat?: boolean } = {}) {
	const run = vi.fn();
	cleanups.push(registerHotkeys(layer, [{ keys, description: keys.join(), run, ...opts }]));
	return run;
}

afterEach(() => {
	cleanups.splice(0).forEach((c) => c());
	setHotkeyHelp(null);
	vi.unstubAllGlobals();
});

describe('dispatch', () => {
	it('runs the bound action and claims the key', () => {
		const run = register(Layer.Reader, ['ArrowRight']);
		const e = key('ArrowRight');
		expect(dispatch(e)).toBe(true);
		expect(run).toHaveBeenCalledOnce();
		expect(e.preventDefault).toHaveBeenCalled();
	});

	it('leaves unbound keys alone', () => {
		register(Layer.Reader, ['ArrowRight']);
		const e = key('x');
		expect(dispatch(e)).toBe(false);
		expect(e.preventDefault).not.toHaveBeenCalled();
	});

	it('gives the key only to the top layer', () => {
		const reader = register(Layer.Reader, ['ArrowLeft', 'Escape']);
		const overlay = register(Layer.Overlay, ['Escape']);
		dispatch(key('Escape'));
		expect(overlay).toHaveBeenCalledOnce();
		expect(reader).not.toHaveBeenCalled();
		// Not bound on top, but lower layers still don't get it.
		expect(dispatch(key('ArrowLeft'))).toBe(false);
		expect(reader).not.toHaveBeenCalled();
	});

	it('hands keys back to the lower layer once the top one is gone', () => {
		const reader = register(Layer.Reader, ['Escape']);
		const close = registerHotkeys(Layer.Overlay, [
			{ keys: ['Escape'], description: 'close', run: vi.fn() }
		]);
		close();
		dispatch(key('Escape'));
		expect(reader).toHaveBeenCalledOnce();
	});

	it('shares a layer between scopes, latest first', () => {
		const pages = register(Layer.Reader, ['ArrowRight', 'Escape']);
		const reader = register(Layer.Reader, ['Escape']);
		dispatch(key('Escape'));
		dispatch(key('ArrowRight'));
		expect(reader).toHaveBeenCalledOnce();
		expect(pages).toHaveBeenCalledOnce();
	});

	it('leaves modifier combinations to the browser', () => {
		const run = register(Layer.Reader, ['ArrowLeft', '+']);
		expect(dispatch(key('ArrowLeft', { altKey: true }))).toBe(false);
		expect(dispatch(key('ArrowLeft', { ctrlKey: true }))).toBe(false);
		expect(dispatch(key('ArrowLeft', { metaKey: true }))).toBe(false);
		expect(run).not.toHaveBeenCalled();
		// Shift is part of typing '+'.
		dispatch(key('+', { shiftKey: true }));
		expect(run).toHaveBeenCalledOnce();
	});

	it('ignores keys typed into fields', () => {
		const run = register(Layer.Reader, ['ArrowLeft']);
		const field = (tagName: string, extra = {}) =>
			({ tagName, ...extra }) as unknown as EventTarget;
		expect(dispatch(key('ArrowLeft', { target: field('INPUT', { type: 'number' }) }))).toBe(false);
		expect(dispatch(key('ArrowLeft', { target: field('TEXTAREA') }))).toBe(false);
		expect(dispatch(key('ArrowLeft', { target: field('SELECT') }))).toBe(false);
		expect(dispatch(key('ArrowLeft', { target: field('DIV', { isContentEditable: true }) }))).toBe(
			false
		);
		expect(run).not.toHaveBeenCalled();
		// A checkbox or button doesn't take arrows as text.
		dispatch(key('ArrowLeft', { target: field('INPUT', { type: 'checkbox' }) }));
		dispatch(key('ArrowLeft', { target: field('BUTTON') }));
		expect(run).toHaveBeenCalledTimes(2);
	});

	it('stays out while a modal is open', () => {
		const run = register(Layer.Reader, ['Escape']);
		vi.stubGlobal('document', { querySelector: () => ({}) });
		expect(dispatch(key('Escape'))).toBe(false);
		expect(run).not.toHaveBeenCalled();
	});

	it('skips auto-repeat unless the key allows it', () => {
		const once = register(Layer.Reader, ['Escape']);
		const held = register(Layer.Reader, ['ArrowRight'], { repeat: true });
		const e = key('Escape', { repeat: true });
		expect(dispatch(e)).toBe(true);
		// Claimed anyway, so a held key doesn't fall through to the browser.
		expect(e.preventDefault).toHaveBeenCalled();
		expect(once).not.toHaveBeenCalled();
		dispatch(key('ArrowRight', { repeat: true }));
		expect(held).toHaveBeenCalledOnce();
	});

	it('ignores events already handled or mid-composition', () => {
		const run = register(Layer.Reader, ['Enter']);
		expect(dispatch(key('Enter', { defaultPrevented: true }))).toBe(false);
		expect(dispatch(key('Enter', { isComposing: true }))).toBe(false);
		expect(run).not.toHaveBeenCalled();
	});
});

describe('registerHotkeys', () => {
	it('listens on the window only while something is registered', () => {
		const add = vi.fn();
		const remove = vi.fn();
		vi.stubGlobal('window', { addEventListener: add, removeEventListener: remove });
		const a = registerHotkeys(Layer.Page, []);
		const b = registerHotkeys(Layer.Reader, []);
		expect(add).toHaveBeenCalledOnce();
		a();
		expect(remove).not.toHaveBeenCalled();
		b();
		expect(remove).toHaveBeenCalledOnce();
		// Unregistering twice is harmless.
		b();
		expect(remove).toHaveBeenCalledOnce();
	});
});

describe('keys the focused element handles', () => {
	it('are never claimed', () => {
		cleanups.push(
			registerHotkeys(Layer.Page, [{ keys: ['Enter'], description: 'Open the selected item' }])
		);
		const e = key('Enter');
		expect(dispatch(e)).toBe(false);
		expect(e.preventDefault).not.toHaveBeenCalled();
	});
});

describe('help', () => {
	it("opens on '?' wherever shortcuts are registered", () => {
		register(Layer.Reader, ['ArrowLeft']);
		const help = vi.fn();
		setHotkeyHelp(help);
		const e = key('?', { shiftKey: true });
		expect(dispatch(e)).toBe(true);
		expect(help).toHaveBeenCalledOnce();
		expect(e.preventDefault).toHaveBeenCalled();
	});

	it("leaves '?' alone without a help handler", () => {
		register(Layer.Reader, ['ArrowLeft']);
		expect(dispatch(key('?'))).toBe(false);
	});

	it('lists the top layer only, latest scope first, each key once', () => {
		register(Layer.Page, ['ArrowLeft', '/']);
		cleanups.push(
			registerHotkeys(Layer.Reader, [
				{ keys: ['ArrowLeft', 'ArrowRight'], description: 'turn', run: vi.fn() }
			]),
			registerHotkeys(Layer.Reader, [
				{ keys: ['Escape'], description: 'close', run: vi.fn() },
				{ keys: ['ArrowLeft'], description: 'shadowed', run: vi.fn() }
			])
		);
		const list = activeHotkeys();
		expect(list.map((h) => h.description)).toEqual(['close', 'shadowed', 'turn']);
		expect(list.find((h) => h.description === 'turn')?.keys).toEqual(['ArrowRight']);
		expect(list.some((h) => h.keys.includes('/'))).toBe(false);
	});

	it('is empty with nothing registered', () => {
		expect(activeHotkeys()).toEqual([]);
	});

	it('shows keys readably', () => {
		expect(keyLabel('ArrowLeft')).toBe('←');
		expect(keyLabel('PageDown')).toBe('PgDn');
		expect(keyLabel('Escape')).toBe('Esc');
		expect(keyLabel('o')).toBe('o');
	});
});
