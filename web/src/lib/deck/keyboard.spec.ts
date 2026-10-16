import { describe, expect, it } from 'vitest';
import { arrowTarget, focusAfterActivate } from './keyboard';
import { SIDEBOARD, emptyLayout, type Layout } from './model';

/** Column 1: a, b, c. Column 4: d. Sideboard: s. Everything else empty. */
function sample(): Layout {
	const layout = emptyLayout();
	layout[1] = ['a', 'b', 'c'];
	layout[4] = ['d'];
	layout[SIDEBOARD] = ['s'];
	return layout;
}

describe('arrowTarget', () => {
	it('moves up and down a column and stops at its ends', () => {
		const layout = sample();
		expect(arrowTarget(layout, 1, 1, 'ArrowUp')).toBe('a');
		expect(arrowTarget(layout, 1, 1, 'ArrowDown')).toBe('c');
		expect(arrowTarget(layout, 1, 0, 'ArrowUp')).toBe('a');
		expect(arrowTarget(layout, 1, 2, 'ArrowDown')).toBe('c');
	});

	it('moves across columns, skipping empty ones, onto the nearest row there is', () => {
		const layout = sample();
		expect(arrowTarget(layout, 1, 2, 'ArrowRight')).toBe('d'); // row 2 doesn't exist: d is last
		expect(arrowTarget(layout, 4, 0, 'ArrowLeft')).toBe('a');
		expect(arrowTarget(layout, 4, 0, 'ArrowRight')).toBe('s');
	});

	it('goes nowhere past the first or last card', () => {
		const layout = sample();
		expect(arrowTarget(layout, 1, 0, 'ArrowLeft')).toBeNull();
		expect(arrowTarget(layout, SIDEBOARD, 0, 'ArrowRight')).toBeNull();
	});

	it('ignores any other key', () => {
		expect(arrowTarget(sample(), 1, 0, 'Tab')).toBeNull();
	});
});

describe('focusAfterActivate', () => {
	it('keeps focus on a card that moved', () => {
		expect(focusAfterActivate(sample(), 'b', 1, 1, false)).toBe('b');
	});

	it('hands focus from a removed basic to the card that took its place', () => {
		// Column 1 after removing a basic that was at row 1: a, b, c.
		expect(focusAfterActivate(sample(), 'x', 1, 1, true)).toBe('b');
		// It was the last card: the new last card.
		expect(focusAfterActivate(sample(), 'x', 1, 3, true)).toBe('c');
		// It was the only card: nowhere.
		expect(focusAfterActivate(sample(), 'x', 0, 0, true)).toBeNull();
	});
});
