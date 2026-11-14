import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { updateProgress } = vi.hoisted(() => ({ updateProgress: vi.fn() }));
vi.mock('$lib/mediaAdapters', () => ({ adapters: { comic: { updateProgress } } }));

import { createProgressReporter, resumePage } from './readingProgress';
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

describe('resumePage', () => {
	const make = (fields: Record<string, unknown>) =>
		({ viewed: true, lastViewed: 0, ...fields }) as unknown as MediaFile;

	it('resumes a partly read comic', () => {
		expect(resumePage(make({ page: 42, lastViewed: 22 }))).toBe(22);
	});

	it('starts over when never opened, on page 1 or finished', () => {
		expect(resumePage(make({ page: 42, lastViewed: 22, viewed: false }))).toBeNull();
		expect(resumePage(make({ page: 42, lastViewed: 1 }))).toBeNull();
		expect(resumePage(make({ page: 42, lastViewed: 42 }))).toBeNull();
		expect(resumePage(make({ page: 42, lastViewed: 50 }))).toBeNull();
	});

	it('has nothing to resume without pages (videos)', () => {
		expect(resumePage(make({ lastViewed: 22 }))).toBeNull();
		expect(resumePage(make({ page: 0, lastViewed: 22 }))).toBeNull();
	});
});
