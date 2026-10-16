// Pure helpers for the deck builder: no network, no DOM, so they are easy to test.
// The builder knows nothing about where its pool came from (Phase 7 reuses it
// with a practice draft's pool), so these types are its own, not the API's.
//
// The layout is the same one the practice draft's pool grid uses: nine
// columns, mana value 0 to 6, then 7+, then the sideboard. A card is
// identified by its `key`, not its card id, so two copies of one card are two
// different things to move.

export const DECK_SIZE = 40;
export const COLUMNS = 9;
export const SIDEBOARD = 8; // the last column; 0 to 7 are the deck
export const MAX_CARDS = 50; // per column
export const HEADERS = ['0', '1', '2', '3', '4', '5', '6', '7+', 'Sideboard'];

/** One card of the pool. A card drafted twice is two entries with different `key`s. */
export interface PoolCard {
	key: string; // unique within the pool
	id: string; // the card's oracle id; what the server is sent
	name: string;
	cmc: number;
	image: string | null; // a Scryfall image URL, or null for a name box
}

export const BASIC_LANDS = [
	{ colour: 'W', name: 'Plains' },
	{ colour: 'U', name: 'Island' },
	{ colour: 'B', name: 'Swamp' },
	{ colour: 'R', name: 'Mountain' },
	{ colour: 'G', name: 'Forest' }
] as const;

/** A basic land added with a button. Each one is its own entry, so it can be dragged. */
export interface BasicLand {
	key: string;
	colour: string;
}

export type Layout = string[][];

export const emptyLayout = (): Layout => Array.from({ length: COLUMNS }, () => []);

/** The deck column a card of this mana value belongs in: 7 and up share the last. */
export function mvColumn(cmc: number): number {
	return Math.min(Math.max(Math.floor(cmc), 0), SIDEBOARD - 1);
}

/** Every pool card in its mana-value column, sorted by name; the sideboard starts empty. */
export function initialLayout(pool: PoolCard[]): Layout {
	const layout = emptyLayout();
	for (const card of [...pool].sort((a, b) => a.name.localeCompare(b.name))) {
		layout[mvColumn(card.cmc)].push(card.key);
	}
	return layout;
}

/** `key` moved to `index` of column `col`. The column it left closes up. */
export function moveTo(layout: Layout, key: string, col: number, index: number): Layout {
	const next = layout.map((column) => column.filter((k) => k !== key));
	next[col].splice(index, 0, key);
	return next;
}

/** Double-click: a deck card goes to the bottom of the sideboard, a sideboard card to its mana-value column. */
export function flip(layout: Layout, key: string, cmc: number): Layout {
	const from = layout.findIndex((column) => column.includes(key));
	const to = from === SIDEBOARD ? mvColumn(cmc) : SIDEBOARD;
	if (layout[to].length >= MAX_CARDS) return layout; // that column is full
	return moveTo(layout, key, to, layout[to].length);
}

/** The same layout without `key` (a basic land taken out). */
export function without(layout: Layout, key: string): Layout {
	return layout.map((column) => column.filter((k) => k !== key));
}

export function deckKeys(layout: Layout): string[] {
	return layout.slice(0, SIDEBOARD).flat();
}

/** Cards in the deck, basics included: the "37" of "37 / 40". */
export function deckSize(layout: Layout): number {
	return deckKeys(layout).length;
}

/** What the server is sent: oracle ids (one per copy) and a count for each basic colour. */
export function toSubmission(layout: Layout, pool: PoolCard[], basics: BasicLand[]) {
	const card = new Map(pool.map((c) => [c.key, c.id]));
	const basic = new Map(basics.map((b) => [b.key, b.colour]));
	const cards: string[] = [];
	const counts: Record<string, number> = {};
	for (const key of deckKeys(layout)) {
		const id = card.get(key);
		if (id) cards.push(id);
		else {
			const colour = basic.get(key);
			if (colour) counts[colour] = (counts[colour] ?? 0) + 1;
		}
	}
	return { cards, basics: counts };
}
