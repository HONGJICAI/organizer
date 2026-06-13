import type { MediaFile } from './model.svelte';

/**
 * A node in the derived folder tree. The tree is built entirely on the client
 * from each file's `path` string — the backend stores full filesystem paths
 * (os.walk is recursive), so the directory structure is already present and no
 * extra API is needed.
 */
export interface FolderNode {
	/** Last path segment (folder name). Empty string for the root. */
	name: string;
	/** Segments from the tree root to this node, with the common prefix stripped. */
	segments: string[];
	/** Sub-folders, sorted by name. */
	children: FolderNode[];
	/** Files that live directly in this folder, sorted by name. */
	files: MediaFile[];
	/** Recursive count of files in this subtree. */
	totalCount: number;
	/** Recursive count of unread files in this subtree. */
	unreadCount: number;
}

/** Split a path on both POSIX and Windows separators, dropping empty segments. */
function splitPath(p: string): string[] {
	return p.split(/[/\\]+/).filter((s) => s.length > 0);
}

/** Length of the longest directory-segment prefix shared by every entry. */
function commonPrefixLength(segArrays: string[][]): number {
	if (segArrays.length === 0) {
		return 0;
	}
	const first = segArrays[0];
	let len = first.length;
	for (const segs of segArrays) {
		let i = 0;
		while (i < len && i < segs.length && segs[i] === first[i]) {
			i++;
		}
		len = i;
		if (len === 0) {
			break;
		}
	}
	return len;
}

function makeNode(name: string, segments: string[]): FolderNode {
	return { name, segments, children: [], files: [], totalCount: 0, unreadCount: 0 };
}

function computeCounts(node: FolderNode): void {
	let total = node.files.length;
	let unread = node.files.filter((f) => !f.viewed).length;
	for (const child of node.children) {
		computeCounts(child);
		total += child.totalCount;
		unread += child.unreadCount;
	}
	node.totalCount = total;
	node.unreadCount = unread;
}

function sortTree(node: FolderNode): void {
	node.children.sort((a, b) => a.name.localeCompare(b.name));
	node.files.sort((a, b) => a.name.localeCompare(b.name));
	for (const child of node.children) {
		sortTree(child);
	}
}

/**
 * Build a folder tree from a flat list of files. A file is considered to live
 * in the directory that contains it (everything before the last path segment),
 * which is true both for archive comics/videos and for directory-based
 * comics/image albums whose `path` is the unit itself.
 */
export function buildFolderTree(files: MediaFile[]): FolderNode {
	const entries = files.map((file) => ({ file, segs: splitPath(file.path).slice(0, -1) }));
	const prefixLen = commonPrefixLength(entries.map((e) => e.segs));
	const root = makeNode('', []);
	for (const { file, segs } of entries) {
		let node = root;
		for (const seg of segs.slice(prefixLen)) {
			let child = node.children.find((c) => c.name === seg);
			if (!child) {
				child = makeNode(seg, [...node.segments, seg]);
				node.children.push(child);
			}
			node = child;
		}
		node.files.push(file);
	}
	computeCounts(root);
	sortTree(root);
	return root;
}

/** Stable key for a node, used as the `?dir=` URL value. Root is the empty string. */
export function nodeKey(node: FolderNode): string {
	return node.segments.join('/');
}

/** Resolve a `?dir=` key back to its node, or undefined if the path no longer exists. */
export function findNode(root: FolderNode, dirKey: string): FolderNode | undefined {
	if (!dirKey) {
		return root;
	}
	let node = root;
	for (const seg of dirKey.split('/').filter(Boolean)) {
		const child = node.children.find((c) => c.name === seg);
		if (!child) {
			return undefined;
		}
		node = child;
	}
	return node;
}

/** Flatten an entire subtree into a single file list (for "include subfolders"). */
export function collectFiles(node: FolderNode): MediaFile[] {
	const out = [...node.files];
	for (const child of node.children) {
		out.push(...collectFiles(child));
	}
	return out;
}
