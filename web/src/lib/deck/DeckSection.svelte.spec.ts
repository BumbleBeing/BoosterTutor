import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DeckRatingsPanel from './DeckRatingsPanel.svelte';
import { poolFromReview } from './pool';
import { fixtureReview } from '$lib/review/fixture';
import type { DeckReview } from '$lib/api/types';

const metrics = {
	effective_lands: 17,
	land_target: 17,
	mana_short_spell: null,
	mana_short_colors: null,
	mana_required: null,
	mana_available: null,
	notable_omission: null
} as unknown as DeckReview['metrics'];

describe('poolFromReview', () => {
	it('lists every pick in order and prunes basic lands', () => {
		expect(poolFromReview(fixtureReview).map((c) => c.name)).toEqual([
			'Alpha Knight',
			'Beta Bear',
			'Gamma Imp'
		]);
		const withBasic = structuredClone(fixtureReview);
		const first = withBasic.analysis.picks[0].picked;
		withBasic.cards[first].type_line = 'Basic Land — Plains';
		expect(poolFromReview(withBasic)).toHaveLength(2);
	});
});

describe('DeckRatingsPanel', () => {
	it('shows the overall grade, a metric and the land count', async () => {
		render(DeckRatingsPanel, {
			review: {
				ratings: {
					rated: true,
					message: null,
					metrics: [{ metric: 'removal', value: 3, percentile: 50, grade: 'C' }],
					predicted_win_rate: 55.5,
					percentile: 70,
					grade: 'B'
				},
				metrics,
				colour_sources: { W: 8, R: 7.5 },
				cards: {}
			}
		});
		await expect.element(page.getByLabelText('Overall grade B')).toBeVisible();
		await expect.element(page.getByText('3 removal spells')).toBeVisible();
		await expect.element(page.getByText('17.0 effective, target 17')).toBeVisible();
		await expect.element(page.getByText('8 white, 7.5 red')).toBeVisible();
	});

	it('says so when the format has no fitted model', async () => {
		render(DeckRatingsPanel, {
			review: {
				ratings: {
					rated: false,
					message: 'not enough data to rate',
					metrics: [],
					predicted_win_rate: null,
					percentile: null,
					grade: null
				},
				metrics,
				colour_sources: {},
				cards: {}
			}
		});
		await expect.element(page.getByText(/Not enough data to rate/)).toBeVisible();
	});
});
