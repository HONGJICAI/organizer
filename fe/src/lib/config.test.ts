import { beforeEach, describe, expect, it } from 'vitest';
import { config, setDesktopConfig, setMobileConfig, staticBase } from './config.svelte';

describe('device presets', () => {
	beforeEach(() => {
		config.apiServer = 'https://organizer.example';
		config.staticServer = '';
	});

	it('keep the connected API server', () => {
		setDesktopConfig();
		expect(config.apiServer).toBe('https://organizer.example');
		setMobileConfig();
		expect(config.apiServer).toBe('https://organizer.example');
	});
});

describe('staticBase', () => {
	it('falls back to the API server', () => {
		config.apiServer = 'https://organizer.example';
		config.staticServer = '';
		expect(staticBase()).toBe('https://organizer.example');
	});

	it('prefers the Static Server setting', () => {
		config.staticServer = 'https://static.example';
		expect(staticBase()).toBe('https://static.example');
	});
});
