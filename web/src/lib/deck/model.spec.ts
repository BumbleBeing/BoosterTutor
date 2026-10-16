import { describe, expect, it } from 'vitest';
import {
	SIDEBOARD,
	deckSize,
	flip,
	initialLayout,
	moveTo,
	mvColumn,
	toSubmission,
	without,
	type PoolCard
} from './model';

function card(key: string, cmc: number, name = key): PoolCard {
	return { key, id: `id-${key}`, name, cmc, image: null };
}

describe('mvColumn', () => {
	it('uses the mana value, with 7 and up sharing the last deck column', () => {
		expect(mvColumn(0)).toBe(0);
		expect(mvColumn(3)).toBe(3);
		expect(mvColumn(7)).toBe(7);
		expect(mvColumn(11)).toBe(7);
	});
});

describe('initialLayout', () => {
	it('puts every card in its mana-value column by name and leaves the sideboard empty', () => {
		const layout = initialLayout([card('z', 2, 'Zed'), card('a', 2, 'Abe'), card('b', 9)]);
		expect(layout[2]).toEqual(['a', 'z']);
		expect(layout[7]).toEqual(['b']);
		expect(layout[SIDEBOARD]).toEqual([]);
		expect(layout).toHaveLength(9);
	});
});

describe('moving cards', () => {
	const start = initialLayout([card('a', 1), card('b', 1), card('c', 3)]);

	it('drops a card at a position and closes the column it left', () => {
		const next = moveTo(start, 'c', 1, 0);
		expect(next[1]).toEqual(['c', 'a', 'b']);
		expect(next[3]).toEqual([]);
	});

	it('flips a deck card to the sideboard and back to its mana-value column', () => {
		const out = flip(start, 'c', 3);
		expect(out[SIDEBOARD]).toEqual(['c']);
		expect(deckSize(out)).toBe(2);
		expect(flip(out, 'c', 3)[3]).toEqual(['c']);
	});

	it('removes a card entirely', () => {
		expect(deckSize(without(start, 'a'))).toBe(2);
	});
});

describe('toSubmission', () => {
	it('sends deck cards by oracle id and counts basics by colour, leaving the sideboard out', () => {
		const pool = [card('a', 1), card('b', 2)];
		let layout = initialLayout(pool);
		layout = moveTo(layout, 'b1', 0, 0);
		layout = moveTo(layout, 'b2', 0, 0);
		layout = flip(layout, 'b', 2); // b goes to the sideboard
		const basics = [
			{ key: 'b1', colour: 'W' },
			{ key: 'b2', colour: 'W' }
		];
		expect(toSubmission(layout, pool, basics)).toEqual({ cards: ['id-a'], basics: { W: 2 } });
	});
});
