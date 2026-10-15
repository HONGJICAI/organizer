import { describe, expect, it } from 'vitest';
import { config, setDesktopConfig, setMobileConfig } from './config.svelte';

describe('device presets', () => {
	it('keep the connected API server', () => {
		config.apiServer = 'https://organizer.example';
		setDesktopConfig();
		expect(config.apiServer).toBe('https://organizer.example');
		setMobileConfig();
		expect(config.apiServer).toBe('https://organizer.example');
	});
});
