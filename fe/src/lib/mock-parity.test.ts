import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Enforces the repo rule: every backend endpoint the frontend consumes must
// have an MSW handler in src/lib/mock.ts, so mock mode (?mock=1, the Vercel
// preview) covers every feature the UI uses. If this test fails, add the
// missing handler to mock.ts.

const libDir = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(libDir, '..');
const sdkSource = fs.readFileSync(path.join(libDir, 'client', 'sdk.gen.ts'), 'utf8');
const mockSource = fs.readFileSync(path.join(libDir, 'mock.ts'), 'utf8');

const VERBS = ['get', 'post', 'put', 'delete', 'patch'];

// Collapse path params of any style ({id}, :id, ${id}) so URLs from the SDK,
// raw fetch template literals, and msw handlers all compare equal.
const normalize = (url: string) =>
	url
		.split('/')
		.map((seg) => (/^\{.*\}$/.test(seg) || seg.startsWith(':') || seg.includes('${') ? ':p' : seg))
		.join('/');

function walk(dir: string): string[] {
	return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const p = path.join(dir, entry.name);
		if (entry.isDirectory()) return entry.name === 'client' ? [] : walk(p);
		const isSource = /\.(ts|svelte)$/.test(entry.name) && !/\.test\.ts$/.test(entry.name);
		return isSource && entry.name !== 'mock.ts' ? [p] : [];
	});
}

// sdk.gen.ts: method name -> "verb /api/path"
const sdkEndpoints = new Map<string, string>();
for (const block of sdkSource.split('public static ').slice(1)) {
	const name = block.match(/^(\w+)/)?.[1];
	const verb = block.match(/\)\.(get|post|put|delete|patch)</)?.[1];
	const url = block.match(/url: '([^']+)'/)?.[1];
	if (name && verb && url) sdkEndpoints.set(name, `${verb} ${normalize(url)}`);
}

// mock.ts: registered handlers as "verb /api/path"
const mockHandlers = new Set<string>();
for (const m of mockSource.matchAll(/http\.(get|post|put|delete|patch)\('([^']+)'/g)) {
	mockHandlers.add(`${m[1]} ${normalize(m[2])}`);
}

// Everything the frontend consumes: SDK service calls (exact verb) and raw
// fetch/img URLs (verb unknown — any handler on the path counts).
const consumed = new Map<string, string>(); // endpoint -> example source file
for (const file of walk(srcDir)) {
	const source = fs.readFileSync(file, 'utf8');
	const rel = path.relative(srcDir, file);
	for (const m of source.matchAll(/\b[A-Z][A-Za-z]*Service\.([a-zA-Z]+)\(/g)) {
		const endpoint = sdkEndpoints.get(m[1]);
		if (endpoint && !consumed.has(endpoint)) consumed.set(endpoint, rel);
	}
	for (const m of source.matchAll(/\/api\/[A-Za-z0-9/${}_.-]+/g)) {
		const endpoint = `any ${normalize(m[0])}`;
		if (!consumed.has(endpoint)) consumed.set(endpoint, rel);
	}
}

describe('mock.ts parity with consumed backend endpoints', () => {
	it('extracts endpoints from sdk.gen.ts, mock.ts and the app source', () => {
		expect(sdkEndpoints.size).toBeGreaterThan(10);
		expect(mockHandlers.size).toBeGreaterThan(10);
		expect(consumed.size).toBeGreaterThan(10);
	});

	it('has an MSW handler for every endpoint the frontend uses', () => {
		const missing: string[] = [];
		for (const [endpoint, source] of consumed) {
			const [verb, url] = endpoint.split(' ');
			const covered =
				verb === 'any'
					? VERBS.some((v) => mockHandlers.has(`${v} ${url}`))
					: mockHandlers.has(endpoint);
			if (!covered) missing.push(`${endpoint} (used in ${source})`);
		}
		expect(missing, 'add MSW handlers in src/lib/mock.ts for these endpoints').toEqual([]);
	});
});
