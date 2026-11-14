import { afterEach, describe, expect, it, vi } from 'vitest';
import { dispatch, Layer, registerHotkeys } from './hotkeys';

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
