import { describe, expect, it } from 'vitest';
import { folderName, hasTag } from './moveTarget';

describe('hasTag', () => {
	it('matches whole tags only', () => {
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', 'Alice')).toBe(true);
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', ' Parody ')).toBe(true);
		expect(hasTag('[Alicetta] Title.zip', 'Alice')).toBe(false);
		expect(hasTag('[Alice] Title.zip', '')).toBe(false);
	});
});

describe('hasTag with several names', () => {
	it('matches any of them', () => {
		expect(hasTag('[Alice EN] Title.zip', ['アリス', 'Alice EN'])).toBe(true);
		expect(hasTag('[Bob] Title.zip', ['アリス', 'Alice EN'])).toBe(false);
		expect(hasTag('[Bob] Title.zip', [' '])).toBe(false);
	});
});

describe('folderName', () => {
	it('matches mover.folder_name', () => {
		expect(folderName(' A:B*C?"D<E>F|G\x01 ')).toBe('A_B_C__D_E_F_G_');
		expect(folderName('Name. .')).toBe('Name');
		expect(folderName('a/b\\c')).toBe('a_b_c');
	});
});
