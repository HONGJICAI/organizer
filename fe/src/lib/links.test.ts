import { describe, expect, it } from 'vitest';
import { withMockParams, withoutMockParams } from './links';

describe('mock params on new-tab links', () => {
	it('leaves links alone without mock mode', () => {
		expect(withMockParams('/comic?q=a%20b', null)).toBe('/comic?q=a%20b');
	});

	it('adds the params that start mock mode again', () => {
		expect(withMockParams('/comic/7', { auth: false })).toBe('/comic/7?mock=1');
		expect(withMockParams('/comic?q=x', { auth: true })).toBe('/comic?q=x&mock=1&auth=1');
	});

	it('drops them once mock mode has started, keeping the rest', () => {
		expect(withoutMockParams('http://host/comic/tag?view=classify&mock=1&auth=1')).toBe(
			'/comic/tag?view=classify'
		);
		expect(withoutMockParams('http://host/?mock=1')).toBe('/');
	});
});
