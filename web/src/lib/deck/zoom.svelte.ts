// Right-click zoom: one card at a time, drawn at 2.5x on top of everything.
// (Ported from the practice draft's pool grid.)
//
// The enlarged copy ignores the pointer (pointer-events: none), so the mouse
// is still "on" the original card underneath it. Moving off that card,
// starting a drag, or right-clicking again shrinks it back.

export const zoom = $state<{
	key: string | null;
	src: string | null;
	name: string;
	rect: DOMRect | null;
}>({ key: null, src: null, name: '', rect: null });

/** Use as a card's oncontextmenu handler. `key` identifies the card on screen. */
export function toggleZoom(event: MouseEvent, key: string, src: string | null, name: string) {
	event.preventDefault(); // no browser menu
	if (zoom.key === key) return clearZoom();
	zoom.key = key;
	zoom.src = src;
	zoom.name = name;
	zoom.rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
}

export function clearZoom(key?: string) {
	if (key !== undefined && zoom.key !== key) return;
	zoom.key = zoom.src = zoom.rect = null;
}
