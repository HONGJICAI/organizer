import { describe, expect, it } from 'vitest';
import { checkName, splitExtension } from './nameCheck';
import { separateFilename } from './utility';

const kinds = (name: string) => checkName(name).map((p) => [p.kind, p.at]);

describe('checkName', () => {
	it('passes well-formed names', () => {
		expect(checkName('[Author] Title (Vol.1) 【DL版】.zip')).toEqual([]);
		// Other bracket types may nest: the splitter only matches the same type.
		expect(checkName('[Author (Circle)] Title.zip')).toEqual([]);
	});

	it('finds an unclosed bracket, which loses every tag', () => {
		const name = '[Author] (Event Title.zip';
		expect(kinds(name)).toEqual([['unclosed', 9]]);
		expect(separateFilename(name)).toEqual([]);
	});

	it('suggests the closer used instead', () => {
		const [p] = checkName('【Author] Title.zip');
		expect(p.kind).toBe('unclosed');
		expect(p.message).toContain('closed with “]” instead?');
		expect(checkName('[Author Title.zip')[0].message).not.toContain('instead');
	});

	it('finds a nested bracket of the same type', () => {
		const name = '[Author [Group]] Title.zip';
		expect(kinds(name)).toEqual([
			['nested', 8],
			['stray', 15]
		]);
		expect(separateFilename(name)).toEqual(['Author [Group', '] Title.zip']);
	});

	it('finds stray closers and empty brackets', () => {
		expect(kinds('[A] Author] Title.zip')).toEqual([['stray', 10]]);
		expect(kinds('[] Title ( ).zip')).toEqual([
			['empty', 0],
			['empty', 9]
		]);
	});

	it('flags names without tags', () => {
		expect(kinds('Title.zip')).toEqual([['untagged', -1]]);
		// A stray closer alone doesn't make a tag.
		expect(kinds('Title).zip')).toEqual([
			['stray', 5],
			['untagged', -1]
		]);
	});
});

describe('splitExtension', () => {
	it('splits archive extensions only', () => {
		expect(splitExtension('[A] T.ZIP')).toEqual(['[A] T', '.ZIP']);
		expect(splitExtension('[A] T.rar')).toEqual(['[A] T', '.rar']);
		expect(splitExtension('[A] Vol.1')).toEqual(['[A] Vol.1', '']);
	});
});
