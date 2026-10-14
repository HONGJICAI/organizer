// Formatting and axis helpers for the stats page. Pure so they can be tested
// without the page.

/** Bytes as a short human size: 0 B, 512 KB, 3.4 MB, 1.25 GB. */
export function formatBytes(bytes: number): string {
	const units = ['B', 'KB', 'MB', 'GB', 'TB'];
	let value = bytes;
	let i = 0;
	while (value >= 1024 && i < units.length - 1) {
		value /= 1024;
		i++;
	}
	const digits = i === 0 || value >= 100 ? 0 : value >= 10 ? 1 : 2;
	return `${value.toFixed(digits)} ${units[i]}`;
}

/** Count with thousands compacted: 999, 1.2K, 12K, 3.4M. */
export function compact(n: number): string {
	if (n < 1000) return String(n);
	const [value, unit] = n < 1e6 ? [n / 1e3, 'K'] : [n / 1e6, 'M'];
	return `${value >= 10 ? Math.round(value) : value.toFixed(1).replace(/\.0$/, '')}${unit}`;
}

/** Smallest 1/2/5×10ⁿ at or above `max`, so the top gridline is a clean number. */
export function niceMax(max: number): number {
	if (max <= 0) return 1;
	const magnitude = 10 ** Math.floor(Math.log10(max));
	for (const step of [1, 2, 5, 10]) {
		if (step * magnitude >= max) return step * magnitude;
	}
	return 10 * magnitude;
}

/** niceMax for a byte count, rounded in the unit formatBytes will show it in. */
export function niceBytes(max: number): number {
	let unit = 1;
	while (max >= unit * 1024 && unit < 1024 ** 4) unit *= 1024;
	return niceMax(max / unit) * unit;
}

/** Full name of a `YYYY-MM` month: `September 2026`. */
export function monthTitle(month: string): string {
	const [y, m] = month.split('-').map(Number);
	return new Date(y, m - 1, 1).toLocaleString('en', { month: 'long', year: 'numeric' });
}

/** Short label for a `YYYY-MM` month: `Jan`, or `Jan 26` when the year changes. */
export function monthLabel(month: string, withYear: boolean): string {
	const [y, m] = month.split('-').map(Number);
	const name = new Date(y, m - 1, 1).toLocaleString('en', { month: 'short' });
	return withYear ? `${name} ${String(y).slice(2)}` : name;
}

/** Which of `count` axis labels to show so at most `maxLabels` appear, always keeping the last. */
export function labelEvery(count: number, maxLabels: number): (i: number) => boolean {
	const step = Math.max(1, Math.ceil(count / maxLabels));
	return (i) => (count - 1 - i) % step === 0;
}
