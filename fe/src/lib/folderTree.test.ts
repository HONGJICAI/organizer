import { describe, it, expect } from 'vitest';
import { buildFolderTree, findNode, nodeKey, collectFiles, type FolderNode } from './folderTree';
import type { MediaFile } from './model.svelte';

/** Minimal stub — buildFolderTree only reads path / name / viewed / size. */
function file(path: string, opts: { viewed?: boolean; size?: number } = {}): MediaFile {
	const name =
		path
			.split(/[/\\]+/)
			.filter(Boolean)
			.pop() ?? '';
	return {
		path,
		name,
		viewed: opts.viewed ?? false,
		size: opts.size ?? 0
	} as unknown as MediaFile;
}

function childNames(node: FolderNode): string[] {
	return node.children.map((c) => c.name);
}

describe('buildFolderTree', () => {
	it('strips the common prefix and nests by directory', () => {
		const tree = buildFolderTree([
			file('/data/comics/AuthorA/Series1/book.zip'),
			file('/data/comics/AuthorA/Series2/book.zip'),
			file('/data/comics/AuthorB/book.zip')
		]);
		// common prefix /data/comics is stripped, so the root holds AuthorA + AuthorB
		expect(childNames(tree)).toEqual(['AuthorA', 'AuthorB']);
		expect(tree.files).toHaveLength(0);
		expect(tree.totalCount).toBe(3);

		const authorA = findNode(tree, 'AuthorA')!;
		expect(childNames(authorA)).toEqual(['Series1', 'Series2']);
		expect(findNode(tree, 'AuthorA/Series1')!.files).toHaveLength(1);
		expect(findNode(tree, 'AuthorB')!.files).toHaveLength(1);
	});

	it('degrades to a flat list when every file is in the same folder', () => {
		const tree = buildFolderTree([
			file('/data/comics/a.zip'),
			file('/data/comics/b.zip'),
			file('/data/comics/c.zip')
		]);
		expect(tree.children).toHaveLength(0);
		expect(tree.files).toHaveLength(3);
		// sorted by name
		expect(tree.files.map((f) => f.name)).toEqual(['a.zip', 'b.zip', 'c.zip']);
	});

	it('keeps multiple scan roots as separate top-level folders', () => {
		const tree = buildFolderTree([file('/data/images/album1'), file('/data/liked/album2')]);
		// no shared prefix beyond /data, so /data is the common prefix
		expect(childNames(tree)).toEqual(['images', 'liked']);
	});

	it('handles a single file', () => {
		const tree = buildFolderTree([file('/data/comics/AuthorA/only.zip')]);
		expect(tree.children).toHaveLength(0);
		expect(tree.files).toHaveLength(1);
		expect(tree.totalCount).toBe(1);
	});

	it('handles Windows-style separators', () => {
		const tree = buildFolderTree([
			file('D:\\manga\\AuthorA\\book.zip'),
			file('D:\\manga\\AuthorB\\book.zip')
		]);
		expect(childNames(tree)).toEqual(['AuthorA', 'AuthorB']);
	});

	it('aggregates total and unread counts recursively', () => {
		const tree = buildFolderTree([
			file('/data/comics/A/x.zip', { viewed: true }),
			file('/data/comics/A/y.zip', { viewed: false }),
			file('/data/comics/B/z.zip', { viewed: false })
		]);
		expect(tree.totalCount).toBe(3);
		expect(tree.unreadCount).toBe(2);
		const a = findNode(tree, 'A')!;
		expect(a.totalCount).toBe(2);
		expect(a.unreadCount).toBe(1);
	});

	it('aggregates total size recursively', () => {
		const tree = buildFolderTree([
			file('/data/comics/A/x.zip', { size: 10 }),
			file('/data/comics/A/sub/y.zip', { size: 5 }),
			file('/data/comics/B/z.zip', { size: 2 })
		]);
		expect(tree.totalSize).toBe(17);
		expect(findNode(tree, 'A')!.totalSize).toBe(15);
		expect(findNode(tree, 'B')!.totalSize).toBe(2);
	});

	it('returns an empty root for no files', () => {
		const tree = buildFolderTree([]);
		expect(tree.children).toHaveLength(0);
		expect(tree.files).toHaveLength(0);
		expect(tree.totalCount).toBe(0);
	});
});

describe('findNode / nodeKey', () => {
	it('round-trips a node through its key', () => {
		const tree = buildFolderTree([file('/data/comics/A/x.zip'), file('/data/comics/B/y.zip')]);
		const child = tree.children[0];
		expect(nodeKey(tree)).toBe('');
		expect(findNode(tree, nodeKey(child))).toBe(child);
	});

	it('returns the root for an empty key', () => {
		const tree = buildFolderTree([file('/data/comics/A/book.zip')]);
		expect(findNode(tree, '')).toBe(tree);
	});

	it('returns undefined for a path that no longer exists', () => {
		const tree = buildFolderTree([file('/data/comics/A/book.zip')]);
		expect(findNode(tree, 'A/Missing')).toBeUndefined();
	});
});

describe('collectFiles', () => {
	it('flattens an entire subtree', () => {
		const tree = buildFolderTree([
			file('/data/comics/A/x.zip'),
			file('/data/comics/A/sub/y.zip'),
			file('/data/comics/B/z.zip')
		]);
		expect(collectFiles(tree)).toHaveLength(3);
		expect(collectFiles(findNode(tree, 'A')!)).toHaveLength(2);
	});
});
