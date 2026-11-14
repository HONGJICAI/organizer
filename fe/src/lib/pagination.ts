// How many slots a Carbon PaginationNav gets for a bar this wide. Carbon
// counts its two "…" overflow menus as slots, so `shown={5}` leaves just three
// page numbers (1 … 5 … 8). Each slot and each arrow button is 3rem; the count
// is odd so the current page sits in the middle, from 5 on a phone up to 11.
const SLOT_PX = 48;
const MIN_SHOWN = 5;
const MAX_SHOWN = 11;

export function paginationShown(barWidth: number | undefined): number {
	if (!barWidth || !Number.isFinite(barWidth)) return MIN_SHOWN;
	// Two arrow buttons, plus one slot of breathing room.
	const slots = Math.floor(barWidth / SLOT_PX) - 3;
	const odd = slots % 2 === 0 ? slots - 1 : slots;
	return Math.min(MAX_SHOWN, Math.max(MIN_SHOWN, odd));
}
