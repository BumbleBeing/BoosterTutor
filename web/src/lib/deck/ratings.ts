// Plain-words labels for the Deck Ratings panel. Pure, so they are easy to test.
// The server computes every number; this only decides how to say it.

import type { DeckMetrics, DeckReview, Grade, MetricRating } from '$lib/api/types';

export const GRADE_STYLE: Record<Grade, string> = {
	A: 'bg-emerald-100 text-emerald-900 ring-emerald-600/30',
	B: 'bg-lime-100 text-lime-900 ring-lime-600/30',
	C: 'bg-amber-100 text-amber-900 ring-amber-600/30',
	D: 'bg-orange-100 text-orange-900 ring-orange-600/30',
	F: 'bg-red-100 text-red-900 ring-red-600/30'
};

const COLOUR_NAMES: Record<string, string> = {
	W: 'white',
	U: 'blue',
	B: 'black',
	R: 'red',
	G: 'green'
};

const n1 = (x: number) => x.toFixed(1);
const signed = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(1)}`;

/** The metric's name and its value in words, in the order the panel lists them. */
export const METRIC_ROWS: Record<string, { label: string; say: (v: number) => string }> = {
	card_quality: { label: 'Card quality', say: (v) => `${signed(v)} pp above the format average` },
	curve_distance: {
		label: 'Mana curve',
		say: (v) => (v === 0 ? 'matches the format’s ideal curve' : `${v} cards off the ideal curve`)
	},
	synergy: { label: 'Synergy', say: (v) => `${signed(v)} pp from card pairings` },
	creatures: { label: 'Creatures', say: (v) => `${v} creatures` },
	removal: { label: 'Removal', say: (v) => `${v} removal spells` },
	mana_shortfall: {
		label: 'Colour sources',
		say: (v) => (v === 0 ? 'every spell has enough sources' : `${n1(v)} sources short at worst`)
	},
	land_distance: {
		label: 'Land count',
		say: (v) => (v === 0 ? 'on target' : `${n1(v)} lands from the target`)
	}
};

export function metricLabel(m: MetricRating): string {
	return METRIC_ROWS[m.metric]?.label ?? m.metric;
}

export function metricSays(m: MetricRating): string {
	return METRIC_ROWS[m.metric]?.say(m.value) ?? n1(m.value);
}

/** "8 white, 7.5 black" for the Colour Sources line. */
export function sourcesLine(sources: Record<string, number>): string {
	const order = 'WUBRG';
	return [...Object.entries(sources)]
		.sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
		.map(([c, n]) => `${Number.isInteger(n) ? n : n1(n)} ${COLOUR_NAMES[c] ?? c}`)
		.join(', ');
}

/** The one thing worth saying about the mana, or null when it is fine. */
export function shortSpellLine(m: DeckMetrics, review: DeckReview): string | null {
	if (!m.mana_short_spell || m.mana_required == null || m.mana_available == null) return null;
	const name = review.cards[m.mana_short_spell]?.name ?? 'A spell';
	const colours = [...(m.mana_short_colors ?? '')].map((c) => COLOUR_NAMES[c] ?? c).join(' or ');
	return `${name} needs ${m.mana_required} ${colours} sources; your deck has ${Number.isInteger(m.mana_available) ? m.mana_available : n1(m.mana_available)}.`;
}

export function omissionLine(m: DeckMetrics, review: DeckReview): string | null {
	const o = m.notable_omission;
	if (!o) return null;
	const name = review.cards[o.oracle_id]?.name ?? 'A sideboard card';
	const weak = review.cards[o.instead_of]?.name ?? 'your weakest playable';
	return `${name} (${n1(o.gih_wr)}% GIH WR) is in your sideboard while ${weak} (${n1(o.instead_of_gih_wr)}%) is in your deck.`;
}
