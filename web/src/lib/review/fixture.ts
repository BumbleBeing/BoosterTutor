// A tiny hand-made review for tests: one pack of three picks.
import type { DraftReview, PickAnalysis } from '$lib/api/types';

const A = 'aaaaaaaa-0000-0000-0000-000000000001';
const B = 'bbbbbbbb-0000-0000-0000-000000000002';
const C = 'cccccccc-0000-0000-0000-000000000003';

function card(name: string) {
	return {
		name,
		mana_cost: null,
		type_line: 'Creature',
		cmc: 2,
		colors: 'W',
		rarity: 'common',
		image_normal: `https://cards.scryfall.io/${name}.jpg`,
		image_art_crop: null
	};
}

function pick(n: number, picked: string, verdict: PickAnalysis['verdict'], noted: boolean) {
	return {
		pack_number: 1,
		pick_number: n,
		picked,
		verdict,
		best: A,
		gap: picked === A ? 0 : 3.4,
		narrow: false,
		noted,
		pool: { size: n - 1, predicted_archetype: n === 3 ? 'WU' : null },
		cards: [
			{
				oracle_id: A,
				scored: true,
				total: 58,
				gih_wr: 58.2,
				games: 900,
				insufficient_data: false,
				fitness_class: 'solid'
			},
			{
				oracle_id: B,
				scored: true,
				total: 54.6,
				gih_wr: 54.1,
				games: 900,
				insufficient_data: false,
				fitness_class: 'questionable'
			},
			{
				oracle_id: C,
				scored: true,
				total: 50,
				gih_wr: 49.9,
				games: 40,
				insufficient_data: true,
				fitness_class: 'mistake'
			}
		]
	} satisfies PickAnalysis;
}

export const fixtureReview: DraftReview = {
	draft_id: '0'.repeat(32),
	set_code: 'hob',
	event_type: 'PremierDraft',
	drafted_at: null,
	wins: 5,
	losses: 2,
	pack_size: 3,
	analysis: {
		stats_snapshot: '2026-10-14',
		picks: [
			pick(1, A, 'solid', false),
			pick(2, B, 'questionable', true),
			pick(3, C, 'mistake', true)
		]
	},
	verdict_counts: { solid: 1, questionable: 1, mistake: 1 },
	noted_picks: [
		[1, 2],
		[1, 3]
	],
	cards: { [A]: card('Alpha Knight'), [B]: card('Beta Bear'), [C]: card('Gamma Imp') }
};
