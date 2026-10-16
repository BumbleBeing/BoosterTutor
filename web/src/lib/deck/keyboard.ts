// Keyboard movement around the deck builder's grid. Pure: given the layout
// and where focus is, it says which card should have focus next, and the
// builder focuses it.

import { COLUMNS, type Layout } from './model';

/**
 * The card an arrow key moves focus to from position `row` of column `col`,
 * or null when there is nowhere to go (or the key isn't an arrow).
 * Up and down move within a column and stop at its ends. Left and right move
 * across columns, skip empty ones, and keep the same row where they can,
 * otherwise landing on the new column's last card.
 */
export function arrowTarget(layout: Layout, col: number, row: number, key: string): string | null {
	let c = col;
	let r = row;
	if (key === 'ArrowUp') r--;
	else if (key === 'ArrowDown') r++;
	else if (key === 'ArrowLeft') c--;
	else if (key === 'ArrowRight') c++;
	else return null;
	// Skip empty columns when moving sideways.
	while (c >= 0 && c < COLUMNS && key === 'ArrowLeft' && !layout[c].length) c--;
	while (c >= 0 && c < COLUMNS && key === 'ArrowRight' && !layout[c].length) c++;
	if (c < 0 || c >= COLUMNS || !layout[c].length) return null;
	r = Math.min(Math.max(r, 0), layout[c].length - 1);
	return layout[c][r];
}

/**
 * Which card keeps focus after Enter acted on `key` at position `row` of
 * column `col`. A moved card keeps it (it is still on screen, just elsewhere).
 * A removed basic land hands it to whichever card took its place, or the
 * column's new last card; null if the column is now empty.
 */
export function focusAfterActivate(
	layout: Layout,
	key: string,
	col: number,
	row: number,
	removed: boolean
): string | null {
	if (!removed) return key;
	return layout[col][Math.min(row, layout[col].length - 1)] ?? null;
}
