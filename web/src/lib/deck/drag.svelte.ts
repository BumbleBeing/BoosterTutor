// Dragging a card around the deck builder's grid with pointer events, so a
// finger works as well as a mouse. This file owns the drag itself: which card,
// where the pointer is, and whether it has moved far enough to count. Where a
// card would land is the builder's question (see `dropTarget` in grid.ts), and
// what a finished move does is the builder's too: this only reports it.
//
// It's a class rather than one shared object (like zoom.svelte.ts) so each
// builder on a page gets its own drag. Its `$state` fields are reactive, so
// markup that reads `drag.dragging` or `drag.target` redraws as they change.

import type { DropTarget } from './grid';

/** How far, in px, the pointer must move before a press becomes a drag. */
export const DRAG_THRESHOLD = 5;

export interface Dragging {
	key: string;
	fromCol: number;
	pointerId: number;
	startX: number;
	startY: number;
	x: number; // where the pointer is now
	y: number;
	grabX: number; // where on the card it was grabbed, so it doesn't jump
	grabY: number;
	active: boolean; // false until the pointer has moved DRAG_THRESHOLD px
}

export interface DragOptions {
	/** Where `key` would land if dropped at (`x`, `y`) in the window, or null if nowhere. */
	locate: (x: number, y: number, key: string, fromCol: number) => DropTarget | null;
	/** A press has just become a drag. */
	onStart?: () => void;
	/** A card was dropped somewhere it's allowed to go. */
	onDrop: (key: string, target: DropTarget) => void;
}

export class DragController {
	/** The press or drag under way, or null. */
	dragging = $state<Dragging | null>(null);
	/** Where the card would land right now, once the drag is active. */
	target = $state<DropTarget | null>(null);

	#options: DragOptions;

	constructor(options: DragOptions) {
		this.#options = options;
	}

	/** The key of the card being dragged, once it has really started moving. */
	get activeKey(): string | null {
		return this.dragging?.active ? this.dragging.key : null;
	}

	// The handlers are arrow functions so they can be passed straight to markup
	// (`onpointermove={drag.move}`) without losing `this`.

	/** A card's onpointerdown. Only the main button (or a finger) starts a drag. */
	down = (event: PointerEvent, key: string, fromCol: number) => {
		if (event.button !== 0) return;
		const el = event.currentTarget as HTMLElement;
		try {
			el.setPointerCapture(event.pointerId); // keeps the drag going outside the card
		} catch {
			// No such active pointer (a synthetic event): the drag still works.
		}
		const rect = el.getBoundingClientRect();
		this.dragging = {
			key,
			fromCol,
			pointerId: event.pointerId,
			startX: event.clientX,
			startY: event.clientY,
			x: event.clientX,
			y: event.clientY,
			grabX: event.clientX - rect.left,
			grabY: event.clientY - rect.top,
			active: false
		};
	};

	move = (event: PointerEvent) => {
		const d = this.dragging;
		if (!d || event.pointerId !== d.pointerId) return;
		d.x = event.clientX;
		d.y = event.clientY;
		// A press that barely moves is a click (or half a double-click), not a drag.
		if (!d.active && Math.hypot(d.x - d.startX, d.y - d.startY) > DRAG_THRESHOLD) {
			d.active = true;
			this.#options.onStart?.();
		}
		if (d.active) this.target = this.#options.locate(d.x, d.y, d.key, d.fromCol);
	};

	up = (event: PointerEvent) => {
		const d = this.dragging;
		if (!d || event.pointerId !== d.pointerId) return;
		const where = d.active
			? this.#options.locate(event.clientX, event.clientY, d.key, d.fromCol)
			: null;
		this.cancel();
		if (where?.allowed) this.#options.onDrop(d.key, where);
	};

	/** The browser took the pointer away (a scroll, a system gesture): drop nothing. */
	cancel = () => {
		this.dragging = null;
		this.target = null;
	};
}
