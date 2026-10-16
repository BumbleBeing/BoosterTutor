import { describe, expect, it } from 'vitest';
import { columnOf, deckSize, emptyBasics, inColumns, toSubmission, type PoolCard } from './model';

function card(name: string, cmc: number, typeLine = 'Creature — Elf'): PoolCard {
	return { key: name, id: `id-${name}`, name, manaCost: null, typeLine, cmc, colors: 'G' };
}

describe('columnOf', () => {
	it('buckets mana values like the server: 0 with 1, 7 and up with 6', () => {
		expect(columnOf(card('a', 0))).toBe('1');
		expect(columnOf(card('b', 3))).toBe('3');
		expect(columnOf(card('c', 6))).toBe('6+');
		expect(columnOf(card('d', 9))).toBe('6+');
	});

	it('puts lands in their own column whatever their mana value', () => {
		expect(columnOf(card('Wooded Foothills', 0, 'Land'))).toBe('Land');
		expect(columnOf(card('Dryad Arbor', 1, 'Land Creature — Forest Dryad'))).toBe('Land');
	});
});

describe('inColumns', () => {
	it('sorts each column by name and keeps empty columns', () => {
		const cols = inColumns([card('Zed', 2), card('Abe', 2)]);
		expect(cols).toHaveLength(7);
		expect(cols.find((c) => c.column === '2')?.cards.map((c) => c.name)).toEqual(['Abe', 'Zed']);
		expect(cols.find((c) => c.column === '5')?.cards).toEqual([]);
	});
});

describe('deck size and submission', () => {
	it('counts cards and basics together', () => {
		expect(deckSize(23, { ...emptyBasics(), W: 9, U: 8 })).toBe(40);
	});

	it('sends oracle ids per copy and leaves out basics at zero', () => {
		const sub = toSubmission([card('a', 1), card('a', 1)], { ...emptyBasics(), W: 2 });
		expect(sub).toEqual({ cards: ['id-a', 'id-a'], basics: { W: 2 } });
	});
});
