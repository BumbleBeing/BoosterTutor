import { describe, expect, it } from 'vitest';
import type { DeckMetrics, DeckReview } from '$lib/api/types';
import { omissionLine, shortSpellLine, sourcesLine } from './ratings';

const baseMetrics = {
	mana_short_spell: null,
	mana_short_colors: null,
	mana_required: null,
	mana_available: null,
	notable_omission: null
} as unknown as DeckMetrics;

const review = (metrics: DeckMetrics): DeckReview =>
	({
		metrics,
		cards: { a: { name: 'Fire Giant' }, b: { name: 'Weak Elf' } }
	}) as unknown as DeckReview;

describe('sourcesLine', () => {
	it('lists colours in WUBRG order, with fractions kept', () => {
		expect(sourcesLine({ R: 7.5, W: 8 })).toBe('8 white, 7.5 red');
	});
});

describe('shortSpellLine', () => {
	it('is null when no spell is short', () => {
		expect(shortSpellLine(baseMetrics, review(baseMetrics))).toBeNull();
	});

	it('names the spell, the colour and both numbers', () => {
		const m = {
			...baseMetrics,
			mana_short_spell: 'a',
			mana_short_colors: 'R',
			mana_required: 12,
			mana_available: 8
		};
		expect(shortSpellLine(m, review(m))).toBe('Fire Giant needs 12 red sources; your deck has 8.');
	});
});

describe('omissionLine', () => {
	it('is null without an omission', () => {
		expect(omissionLine(baseMetrics, review(baseMetrics))).toBeNull();
	});

	it('names both cards and their win rates', () => {
		const m = {
			...baseMetrics,
			notable_omission: {
				oracle_id: 'a',
				gih_wr: 60,
				instead_of: 'b',
				instead_of_gih_wr: 52,
				gap: 8
			}
		};
		expect(omissionLine(m, review(m))).toContain('Fire Giant (60.0% GIH WR)');
	});
});
