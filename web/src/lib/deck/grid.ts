// The deck builder's grid geometry: where each card sits and where a dragged
// card would land. Pure numbers in, numbers out (no DOM), so every drop rule
// can be tested without a browser.
//
// The grid is nine columns of cards that overlap so only each card's title
// bar (its "strip") shows, except the last card of a column, which shows whole.

import { COLUMNS, MAX_CARDS, SIDEBOARD, type Layout } from './model';

export const GAP = 8; // px between columns
export const CARD_RATIO = 680 / 488; // height / width of a Scryfall card image
export const STRIP = 0.13; // the share of a card's height its title bar takes
export const MIN_COL = 56; // narrower than this and the grid scrolls sideways instead
export const PADDING = 24; // the grid panel's p-3, both sides

/** The sizes everything else is worked out from, in px. */
export interface Metrics {
	inner: number; // the grid's own width: the panel minus its padding, or wider if it scrolls
	colW: number; // one column (and one card) wide
	cardH: number; // one card tall
	strip: number; // how far down each card sits below the one before it
}

/** The grid's sizes for a panel `panelWidth` px wide (padding included). */
export function metrics(panelWidth: number): Metrics {
	// Never narrower than nine minimum columns: past that the panel scrolls.
	const inner = Math.max(MIN_COL * COLUMNS + GAP * (COLUMNS - 1), panelWidth - PADDING);
	const colW = (inner - GAP * (COLUMNS - 1)) / COLUMNS;
	const cardH = colW * CARD_RATIO;
	return { inner, colW, cardH, strip: cardH * STRIP };
}

/** The left edge of column `col`. */
export const columnLeft = (m: Metrics, col: number) => col * (m.colW + GAP);

/** How tall a column of `n` cards is: n - 1 strips and one whole card. */
export const columnHeight = (m: Metrics, n: number) =>
	n === 0 ? m.cardH : (n - 1) * m.strip + m.cardH;

/** The tallest column's height: the grid's own height. */
export const gridHeight = (m: Metrics, layout: Layout) =>
	Math.max(...layout.map((column) => columnHeight(m, column.length)));

/** Where a dragged card would land, and whether it may. */
export interface DropTarget {
	col: number;
	index: number; // its position in that column once it has left its old place
	allowed: boolean;
}

/** The card being dragged: which one, the column it came from, and whether it's a basic land. */
export interface Dragged {
	key: string;
	fromCol: number;
	basic: boolean;
}

/**
 * Where a card dropped at (`x`, `y`) lands, measured from the grid's top-left
 * corner. The rules:
 *   * onto the card at position n: it takes position n
 *   * below a column: directly under that column's last card
 *   * the column it left closes up, so positions below it count one fewer
 *   * a basic land can't go in the sideboard
 *   * a full column refuses a card, unless the card is already in it
 */
export function dropTarget(
	m: Metrics,
	layout: Layout,
	dragged: Dragged,
	x: number,
	y: number
): DropTarget {
	// Left of the grid counts as the first column, right of it as the last.
	const col = Math.min(COLUMNS - 1, Math.max(0, Math.floor(x / (m.colW + GAP))));
	const column = layout[col];
	const lengthAfter = column.length - (col === dragged.fromCol ? 1 : 0);
	let index: number;
	if (column.length === 0 || y > columnHeight(m, column.length)) {
		index = lengthAfter; // below the column: directly under its last card
	} else {
		// Onto the card at n: take position n. The last card shows whole, so
		// anywhere on it below its strip still counts as that card.
		const n = Math.min(Math.max(0, Math.floor(y / m.strip)), column.length - 1);
		index = Math.min(n, lengthAfter);
	}
	// A basic land can't go in the sideboard: it would just be a card nobody plays.
	const basicInSideboard = col === SIDEBOARD && dragged.basic;
	const allowed = !basicInSideboard && (col === dragged.fromCol || column.length < MAX_CARDS);
	return { col, index, allowed };
}
