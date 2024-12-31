const pairsSeparator = new Map<string, string>([
	['(', ')'],
	['[', ']'],
	['{', '}'],
	['【', '】'],
	['<', '>'],
	['《', '》']
]);
export function separateFilename(filename: string): string[] {
	const parts = filename.split('\\');
	return parts.map((part) => separateFilenameImpl(part)).flat();
}
function separateFilenameImpl(filename: string): string[] {
	const ret: string[] = [];
	let buffer = '';
	for (let i = 0; i < filename.length; i++) {
		if (pairsSeparator.has(filename[i])) {
			if (buffer.length > 0) {
				ret.push(buffer.trim());
				buffer = '';
			}
			const pair = pairsSeparator.get(filename[i]);
			const j = filename.indexOf(pair!, i);
			if (j < 0) {
				return [];
			}
			ret.push(filename.slice(i + 1, j).trim());
			i = j;
		} else {
			buffer += filename[i];
		}
	}
	if (buffer.length > 0) {
		ret.push(buffer.trim());
	}
	return ret.filter((s) => !!s);
}
export function includeAllKeywords(source: string, keywords: string[]): boolean {
	return keywords.every((keyword) => source.includes(keyword));
}
