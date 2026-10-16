import { describe, expect, it } from 'vitest';
import {
	CARD_RATIO,
	GAP,
	MIN_COL,
	PADDING,
	STRIP,
	columnHeight,
	columnLeft,
	dropTarget,
	gridHeight,
	metrics,
	type Dragged
} from './grid';
import { COLUMNS, MAX_CARDS, SIDEBOARD, emptyLayout, type Layout } from './model';

// A panel wide enough for columns exactly 100px wide: easy numbers.
const m = metrics(100 * COLUMNS + GAP * (COLUMNS - 1) + PADDING);
const cardH = 100 * CARD_RATIO;
const strip = cardH * STRIP;

/** The middle of column `col`, and the middle of the strip of card `n` in it. */
const xOf = (col: number) => columnLeft(m, col) + 50;
const yOf = (n: number) => n * strip + strip / 2;

/** Column 2 holds a, b, c; column 3 holds d; everything else is empty. */
function sample(): Layout {
	const layout = emptyLayout();
	layout[2] = ['a', 'b', 'c'];
	layout[3] = ['d'];
	return layout;
}

const card = (key: string, fromCol: number, basic = false): Dragged => ({ key, fromCol, basic });

describe('metrics', () => {
	it('fills the panel, less its padding, with nine columns', () => {
		expect(m.inner).toBe(100 * COLUMNS + GAP * (COLUMNS - 1));
		expect(m.colW).toBeCloseTo(100);
		expect(m.cardH).toBeCloseTo(cardH);
		expect(m.strip).toBeCloseTo(strip);
	});

	it('never shrinks a column below the minimum: a narrow panel scrolls instead', () => {
		const phone = metrics(300);
		expect(phone.colW).toBeCloseTo(MIN_COL);
		expect(phone.inner).toBeGreaterThan(300);
	});
});

describe('heights', () => {
	it('shows one strip per card and the last card whole', () => {
		expect(columnHeight(m, 0)).toBeCloseTo(cardH); // an empty column still takes a card's room
		expect(columnHeight(m, 1)).toBeCloseTo(cardH);
		expect(columnHeight(m, 3)).toBeCloseTo(2 * strip + cardH);
	});

	it('makes the grid as tall as its tallest column', () => {
		expect(gridHeight(m, sample())).toBeCloseTo(2 * strip + cardH);
		expect(gridHeight(m, emptyLayout())).toBeCloseTo(cardH);
	});
});

describe('dropTarget', () => {
	it('picks the column under the pointer, clamping either side of the grid', () => {
		expect(dropTarget(m, sample(), card('d', 3), xOf(5), 0).col).toBe(5);
		expect(dropTarget(m, sample(), card('d', 3), -40, 0).col).toBe(0);
		expect(dropTarget(m, sample(), card('d', 3), m.inner + 40, 0).col).toBe(SIDEBOARD);
	});

	it('gives a card dropped onto card n position n', () => {
		const layout = sample();
		expect(dropTarget(m, layout, card('d', 3), xOf(2), yOf(0)).index).toBe(0);
		expect(dropTarget(m, layout, card('d', 3), xOf(2), yOf(1)).index).toBe(1);
		// Anywhere on the last card, which shows whole, still counts as that card.
		expect(dropTarget(m, layout, card('d', 3), xOf(2), 2 * strip + cardH - 1).index).toBe(2);
	});

	it('puts a card dropped below a column directly under its last card', () => {
		const below = 2 * strip + cardH + 10;
		expect(dropTarget(m, sample(), card('d', 3), xOf(2), below).index).toBe(3);
		// An empty column: the top, wherever the pointer is.
		expect(dropTarget(m, sample(), card('d', 3), xOf(6), yOf(4)).index).toBe(0);
	});

	it('closes up the column a card leaves, so positions count without it', () => {
		const layout = sample();
		// a moves below c in its own column: the column is b, c without it.
		const below = 2 * strip + cardH + 10;
		expect(dropTarget(m, layout, card('a', 2), xOf(2), below).index).toBe(2);
		// Dropped on c, its last card: it can be at most the second card now.
		expect(dropTarget(m, layout, card('a', 2), xOf(2), yOf(2)).index).toBe(2);
		expect(dropTarget(m, layout, card('c', 2), xOf(2), yOf(2)).index).toBe(2);
		// Dropped on itself: it stays.
		expect(dropTarget(m, layout, card('b', 2), xOf(2), yOf(1)).index).toBe(1);
	});

	it("won't take a basic land into the sideboard, but takes any other card", () => {
		expect(dropTarget(m, sample(), card('b0', 0, true), xOf(SIDEBOARD), 0).allowed).toBe(false);
		expect(dropTarget(m, sample(), card('b0', 0, true), xOf(4), 0).allowed).toBe(true);
		expect(dropTarget(m, sample(), card('d', 3), xOf(SIDEBOARD), 0).allowed).toBe(true);
	});

	it('refuses a card a full column, unless the card is already in it', () => {
		const layout = sample();
		layout[5] = Array.from({ length: MAX_CARDS }, (_, i) => `f${i}`);
		expect(dropTarget(m, layout, card('d', 3), xOf(5), 0).allowed).toBe(false);
		expect(dropTarget(m, layout, card('f0', 5), xOf(5), yOf(9)).allowed).toBe(true);
	});
});
