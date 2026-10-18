import { describe, expect, it } from 'vitest';
import { defaultTarget, folderName, hasTag } from './moveTarget';

describe('hasTag', () => {
	it('matches whole tags only', () => {
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', 'Alice')).toBe(true);
		expect(hasTag('[Alice] Title (Parody) [Chinese].zip', ' Parody ')).toBe(true);
		expect(hasTag('[Alicetta] Title.zip', 'Alice')).toBe(false);
		expect(hasTag('[Alice] Title.zip', '')).toBe(false);
	});
});

describe('folderName', () => {
	it('replaces characters folder names cannot hold', () => {
		expect(folderName(' A/B\\C:D*E?F"G<H>I|J ')).toBe('A_B_C_D_E_F_G_H_I_J');
		expect(folderName('Name...')).toBe('Name');
	});
});

describe('defaultTarget', () => {
	it('goes next to the most common folder', () => {
		const paths = [
			'/data/comics/nas/inbox/[Alice] One.zip',
			'/data/comics/nas/inbox/[Alice] Two.zip',
			'/data/comics/other/[Alice] Three.zip'
		];
		expect(defaultTarget(paths, 'Alice')).toBe('/data/comics/nas/inbox/Alice');
	});

	it('keeps a folder already named after the tag', () => {
		const paths = ['/data/comics/Alice/[Alice] One.zip', '/data/comics/Alice/[Alice] Two.zip'];
		expect(defaultTarget(paths, 'Alice')).toBe('/data/comics/Alice');
	});

	it('uses the separator of Windows paths', () => {
		expect(defaultTarget(['D:\\comics\\[A] One.zip'], 'A')).toBe('D:\\comics\\A');
	});

	it('is empty without comics or a usable name', () => {
		expect(defaultTarget([], 'A')).toBe('');
		expect(defaultTarget(['/data/x.zip'], '...')).toBe('');
	});
});
