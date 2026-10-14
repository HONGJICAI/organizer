import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { updateProgress } = vi.hoisted(() => ({ updateProgress: vi.fn() }));
vi.mock('$lib/mediaAdapters', () => ({ adapters: { comic: { updateProgress } } }));

import { createProgressReporter } from './readingProgress';
import type { MediaFile } from './model.svelte';

const file = () => ({ id: 1, type: 'comic', lastViewed: 0 }) as unknown as MediaFile;

describe('createProgressReporter', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		updateProgress.mockClear();
	});
	afterEach(() => vi.useRealTimers());

	it('reports the settled page after the debounce', () => {
		const f = file();
		const r = createProgressReporter(f, 1000);
		r.schedule(2);
		r.schedule(3);
		vi.advanceTimersByTime(1000);
		expect(updateProgress).toHaveBeenCalledTimes(1);
		expect(updateProgress).toHaveBeenCalledWith(1, 3);
		expect(f.lastViewed).toBe(3);
	});

	it('sends nothing while disabled, including on flush', () => {
		const f = file();
		const r = createProgressReporter(f, 1000, () => false);
		r.schedule(4);
		vi.advanceTimersByTime(1000);
		r.flush();
		expect(updateProgress).not.toHaveBeenCalled();
		expect(f.lastViewed).toBe(0);
	});

	it('drops a pending report when disabled during the debounce', () => {
		let enabled = true;
		const r = createProgressReporter(file(), 1000, () => enabled);
		r.schedule(5);
		enabled = false;
		vi.advanceTimersByTime(1000);
		expect(updateProgress).not.toHaveBeenCalled();
	});

	it('reports once enabled again', () => {
		let enabled = false;
		const r = createProgressReporter(file(), 1000, () => enabled);
		r.schedule(5);
		vi.advanceTimersByTime(1000);
		enabled = true;
		r.schedule(5);
		vi.advanceTimersByTime(1000);
		expect(updateProgress).toHaveBeenCalledWith(1, 5);
	});
});
