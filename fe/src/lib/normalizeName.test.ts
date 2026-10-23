import { describe, expect, it } from 'vitest';
import { narrowWidth, normalizeName, rules, type NormalizeRule } from './normalizeName';
import { separateFilename } from './utility';

const all = new Set(rules);
const languages = new Set(['中国翻訳', 'English']);
const isLanguage = (tag: string) => languages.has(tag);
const norm = (name: string, use: ReadonlySet<NormalizeRule> = all) =>
	normalizeName(name, use, isLanguage);

describe('normalizeName', () => {
	it('leaves a clean name alone', () => {
		expect(norm('[Author] Title (C99) [English].zip')).toEqual({
			name: '[Author] Title (C99) [English].zip',
			changed: []
		});
	});

	it('narrows full-width letters, digits and spaces', () => {
		expect(norm('[Ａｕｔｈｏｒ]\u3000Ｔｉｔｌｅ１２.zip')).toEqual({
			name: '[Author] Title12.zip',
			changed: ['width']
		});
		// 【】 and 《》 have no half-width form.
		expect(narrowWidth('【Ａ】《Ｂ》')).toBe('【A】《B》');
	});

	it('keeps full-width symbols', () => {
		// Japanese punctuation, and stand-ins for characters Windows forbids.
		const name = '[A] ご注文は？！～ Ｖｏｌ：１＊＂＜＞｜／＼.zip';
		expect(norm(name).name).toBe('[A] ご注文は？！～ Vol：1＊＂＜＞｜／＼.zip');
		expect(norm('[A] ＞＜ Title.zip').changed).toEqual([]);
	});

	it('narrows full-width brackets, which then read as tags', () => {
		const { name, changed } = norm('［Author］ Title（C99）.zip');
		expect(name).toBe('[Author] Title(C99).zip');
		expect(changed).toEqual(['brackets']);
		expect(separateFilename('［Author］ Title.zip')).toEqual(['［Author］ Title.zip']);
		expect(separateFilename(name)).toEqual(['Author', 'Title', 'C99', '.zip']);
	});

	it('fixes mixed-width pairs', () => {
		expect(norm('[Author］ Title.zip').name).toBe('[Author] Title.zip');
	});

	it('widens half-width katakana, joining voiced marks', () => {
		expect(norm('[A] ｶﾞﾝﾀﾞﾑ.zip')).toEqual({ name: '[A] ガンダム.zip', changed: ['kana'] });
	});

	it('tidies spaces', () => {
		expect(norm(' [A]  Title   2 .zip')).toEqual({ name: '[A] Title 2.zip', changed: ['spaces'] });
	});

	it('moves language tags to the end, keeping their order and brackets', () => {
		expect(norm('[中国翻訳] [Author] Title (English) [DL版].zip')).toEqual({
			name: '[Author] Title [DL版] [中国翻訳] (English).zip',
			changed: ['language']
		});
		// Already last: nothing to do.
		expect(norm('[Author] Title [中国翻訳] [English].zip').changed).toEqual([]);
		// Matched after the width rules ran.
		expect(norm('［中国翻訳］ [Author] Title.zip').name).toBe('[Author] Title [中国翻訳].zip');
	});

	it("doesn't move tags when the brackets don't pair up", () => {
		expect(norm('[English] [Author Title.zip').changed).toEqual([]);
	});

	it('only runs the rules asked for', () => {
		const name = '［中国翻訳］ [Ａuthor]  Title.zip';
		expect(norm(name, new Set(['width'])).name).toBe('［中国翻訳］ [Author]  Title.zip');
		expect(norm(name, new Set(['brackets', 'language']))).toEqual({
			name: '[Ａuthor] Title [中国翻訳].zip',
			changed: ['brackets', 'language']
		});
	});

	it('keeps folder names without an extension whole', () => {
		expect(norm('[A] Vol．１').name).toBe('[A] Vol．1');
	});
});
