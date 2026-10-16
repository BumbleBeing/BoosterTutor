import { describe, expect, it } from 'vitest';
import { fixtureReview } from './fixture';
import {
	archetypeName,
	buildTimeline,
	buildWheels,
	describeError,
	eventName,
	finalArchetype,
	formatFitness,
	formatRecord,
	formatWinRate,
	wheelHeadline
} from './model';

describe('buildTimeline', () => {
	const packs = buildTimeline(fixtureReview);

	it('groups picks into packs in draft order', () => {
		expect(packs).toHaveLength(1);
		expect(packs[0].picks.map((p) => p.pick.pick_number)).toEqual([1, 2, 3]);
	});

	it('lists only higher-scoring cards as alternatives, best first', () => {
		const [first, second, third] = packs[0].picks;
		expect(first.alternatives).toEqual([]); // took the best card
		expect(second.alternatives.map((a) => a.info?.name)).toEqual(['Alpha Knight']);
		expect(third.alternatives.map((a) => a.info?.name)).toEqual(['Alpha Knight', 'Beta Bear']);
	});

	it('ranks alternatives by fitness even when GIH WR disagrees', () => {
		// Beta Bear has the higher fitness but the lower GIH WR. It must still
		// rank first, which is why the page labels it with its fitness.
		const [pick] = fixtureReview.analysis.picks;
		const review = {
			...fixtureReview,
			analysis: {
				...fixtureReview.analysis,
				picks: [
					{
						...pick,
						picked: pick.cards[2].oracle_id,
						cards: [
							{ ...pick.cards[0], total: 55, gih_wr: 60 },
							{ ...pick.cards[1], total: 57, gih_wr: 52 },
							pick.cards[2]
						]
					}
				]
			}
		};
		const [entry] = buildTimeline(review)[0].picks;
		expect(entry.alternatives.map((a) => a.info?.name)).toEqual(['Beta Bear', 'Alpha Knight']);
	});
});

describe('buildWheels', () => {
	const [pack] = buildWheels(fixtureReview);

	it('names the cards and lists the best win rate first', () => {
		expect(pack.pack).toBe(1);
		expect(pack.laps[0].wheeled.map((c) => c.name)).toEqual(['Alpha Knight', 'Beta Bear']);
		expect(pack.laps[0].taken.map((c) => c.name)).toEqual(['Gamma Imp']);
	});

	it('joins each colour to its best card that came back', () => {
		expect(pack.colours[0]).toMatchObject({ colour: 'W', name: 'White', good: 1 });
		expect(pack.colours[0].best?.name).toBe('Alpha Knight');
		expect(pack.colours[1].best).toBeNull();
	});

	it('sums up which colours sent good cards back', () => {
		expect(wheelHeadline(pack)).toBe('Good cards that came back: White 1.');
		const none = { ...pack, colours: pack.colours.map((c) => ({ ...c, good: 0 })) };
		expect(wheelHeadline(none)).toBe('No good card of any colour came back.');
	});
});

describe('formatting', () => {
	it('formats win rates and missing values', () => {
		expect(formatWinRate(56.34)).toBe('56.3%');
		expect(formatWinRate(null)).toBe('—');
	});

	it('formats fitness without a percent sign', () => {
		expect(formatFitness(57.84)).toBe('57.8');
		expect(formatFitness(null)).toBe('—');
	});

	it('names event types in words', () => {
		expect(eventName('PremierDraft')).toBe('Premier Draft');
		expect(eventName('TradDraft')).toBe('Traditional Draft');
		expect(eventName('OpenDraft_HOB_20261001')).toBe('Open Draft');
		expect(eventName('SomeNewDraft_X')).toBe('Some New Draft');
	});

	it('names archetypes', () => {
		expect(archetypeName('WU')).toBe('White-Blue');
		expect(archetypeName(null)).toBeNull();
		expect(finalArchetype(fixtureReview)).toBe('WU');
	});

	it('shows the record only when known', () => {
		expect(formatRecord(fixtureReview)).toBe('5-2');
		expect(formatRecord({ ...fixtureReview, wins: null })).toBeNull();
	});
});

describe('describeError', () => {
	it('gives every kind some copy and marks transient failures retryable', () => {
		expect(
			describeError({ kind: 'upstream_failure', message: '', retryAfter: null }).retryable
		).toBe(true);
		expect(
			describeError({ kind: 'draft_not_found', message: '', retryAfter: null }).retryable
		).toBe(false);
		expect(describeError({ kind: 'unknown', message: '', retryAfter: null }).title).not.toBe('');
	});

	it('says how long to wait when rate limited', () => {
		const copy = describeError({ kind: 'rate_limited', message: '', retryAfter: 30 });
		expect(copy.body).toContain('30 seconds');
	});
});
