// Pure helpers for the deck builder: no network, no DOM, so they are easy to test.
// The builder knows nothing about where its pool came from (Phase 7 reuses it
// with a practice draft's pool), so these types are its own, not the API's.

export const DECK_SIZE = 40;

/** One card of the pool. A card drafted twice is two entries with different `key`s. */
export interface PoolCard {
	key: string; // unique within the pool
	id: string; // the card's oracle id; what the server is sent
	name: string;
	manaCost: string | null;
	typeLine: string;
	cmc: number;
	colors: string; // sorted WUBRG letters, "" for colourless
}

export type Basics = Record<string, number>;

export const BASIC_LANDS = [
	{ colour: 'W', name: 'Plains' },
	{ colour: 'U', name: 'Island' },
	{ colour: 'B', name: 'Swamp' },
	{ colour: 'R', name: 'Mountain' },
	{ colour: 'G', name: 'Forest' }
] as const;

export const emptyBasics = (): Basics => ({ W: 0, U: 0, B: 0, R: 0, G: 0 });

/** Header for the lands column; the others are mana values. */
export const LAND_COLUMN = 'Land';
export const COLUMNS = ['1', '2', '3', '4', '5', '6+', LAND_COLUMN] as const;
export type Column = (typeof COLUMNS)[number];

export function isLand(card: PoolCard): boolean {
	return /\bLand\b/.test(card.typeLine);
}

/**
 * Which column a card sits in. Mana value 0 counts with 1 and 7+ with 6, the
 * same buckets the server's curve uses, so what you see is what is rated.
 */
export function columnOf(card: PoolCard): Column {
	if (isLand(card)) return LAND_COLUMN;
	const mv = Math.min(6, Math.max(1, Math.round(card.cmc)));
	return mv === 6 ? '6+' : (String(mv) as Column);
}

/** Cards grouped into the columns, each sorted by name. Empty columns are kept. */
export function inColumns(cards: PoolCard[]): { column: Column; cards: PoolCard[] }[] {
	return COLUMNS.map((column) => ({
		column,
		cards: cards.filter((c) => columnOf(c) === column).sort((a, b) => a.name.localeCompare(b.name))
	}));
}

export function basicsTotal(basics: Basics): number {
	return Object.values(basics).reduce((sum, n) => sum + n, 0);
}

/** Cards in the deck, basics included: the "37" of "37 / 40". */
export function deckSize(mainCount: number, basics: Basics): number {
	return mainCount + basicsTotal(basics);
}

/** What the server is sent: oracle ids (one per copy) and the basics that were added. */
export function toSubmission(main: PoolCard[], basics: Basics) {
	return {
		cards: main.map((c) => c.id),
		basics: Object.fromEntries(Object.entries(basics).filter(([, n]) => n > 0))
	};
}
