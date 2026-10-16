import { describe, expect, it } from 'vitest';
import { fixtureReview } from './fixture';
import {
	archetypeName,
	buildTimeline,
	describeError,
	finalArchetype,
	formatRecord,
	formatWinRate
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
});

describe('formatting', () => {
	it('formats win rates and missing values', () => {
		expect(formatWinRate(56.34)).toBe('56.3%');
		expect(formatWinRate(null)).toBe('—');
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
