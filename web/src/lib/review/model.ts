// Pure helpers for the review page: no network, no DOM, so they are easy to test.

import type { ApiError } from '$lib/api/client';
import type { CardInfo, CardScore, DraftReview, PickAnalysis, Verdict } from '$lib/api/types';

/** Label and Tailwind classes for each verdict chip. The words matter as much as the colour. */
export const VERDICT_STYLE: Record<Verdict, { label: string; chip: string }> = {
	solid: { label: 'Solid', chip: 'bg-emerald-100 text-emerald-900 ring-emerald-600/30' },
	questionable: { label: 'Questionable', chip: 'bg-amber-100 text-amber-900 ring-amber-600/30' },
	mistake: { label: 'Mistake', chip: 'bg-red-100 text-red-900 ring-red-600/30' },
	indifferent: { label: 'No real choice', chip: 'bg-slate-100 text-slate-700 ring-slate-500/30' }
};

// Display order for the summary counts.
export const VERDICT_ORDER: Verdict[] = ['solid', 'questionable', 'mistake', 'indifferent'];

export interface TimelinePick {
	index: number; // 0-based position in the whole draft
	pick: PickAnalysis;
	taken: CardInfo | undefined;
	takenScore: CardScore | undefined;
	// Better cards the drafter passed, best first (at most three).
	alternatives: { score: CardScore; info: CardInfo | undefined }[];
}

export interface TimelinePack {
	number: number;
	picks: TimelinePick[];
}

/** Join each pick with its card names and the cards that scored higher. */
export function buildTimeline(review: DraftReview): TimelinePack[] {
	const packs = new Map<number, TimelinePick[]>();
	review.analysis.picks.forEach((pick, index) => {
		const takenScore = pick.cards.find((c) => c.oracle_id === pick.picked);
		const takenTotal = takenScore?.total ?? -Infinity;
		const alternatives = pick.cards
			.filter((c) => c.oracle_id !== pick.picked && c.scored && (c.total ?? -Infinity) > takenTotal)
			.slice(0, 3)
			.map((score) => ({ score, info: review.cards[score.oracle_id] }));
		const entry: TimelinePick = {
			index,
			pick,
			taken: review.cards[pick.picked],
			takenScore,
			alternatives
		};
		const list = packs.get(pick.pack_number) ?? [];
		list.push(entry);
		packs.set(pick.pack_number, list);
	});
	return [...packs.entries()].map(([number, picks]) => ({ number, picks }));
}

/** 56.34 -> "56.3%"; missing -> an em dash. */
export function formatWinRate(wr: number | null | undefined): string {
	return wr == null ? '—' : `${wr.toFixed(1)}%`;
}

/** 2.345 -> "2.3 pp" (percentage points short of the best card). */
export function formatGap(gap: number | null): string {
	return gap == null ? '' : `${gap.toFixed(1)} pp`;
}

const COLOR_NAMES: Record<string, string> = {
	W: 'White',
	U: 'Blue',
	B: 'Black',
	R: 'Red',
	G: 'Green'
};

/** "WU" -> "White-Blue"; "W" -> "White"; unknown/empty -> null. */
export function archetypeName(pair: string | null): string | null {
	if (!pair) return null;
	const names = [...pair].map((c) => COLOR_NAMES[c]).filter(Boolean);
	return names.length ? names.join('-') : null;
}

/** The archetype the pool pointed at by the end of the draft. */
export function finalArchetype(review: DraftReview): string | null {
	const picks = review.analysis.picks;
	for (let i = picks.length - 1; i >= 0; i--) {
		const a = picks[i].pool.predicted_archetype;
		if (a) return a;
	}
	return null;
}

/** "5-2", or null when 17Lands didn't give a record. */
export function formatRecord(review: DraftReview): string | null {
	if (review.wins == null || review.losses == null) return null;
	return `${review.wins}-${review.losses}`;
}

export function packLabel(pick: PickAnalysis): string {
	return `Pack ${pick.pack_number}, pick ${pick.pick_number}`;
}

export interface ErrorCopy {
	title: string;
	body: string;
	// Whether trying the same thing again could help.
	retryable: boolean;
}

/** What to tell the person for each failure. Plain words, and what to do next. */
export function describeError(err: Pick<ApiError, 'kind' | 'message' | 'retryAfter'>): ErrorCopy {
	switch (err.kind) {
		case 'invalid_input':
			return {
				title: "That doesn't look like a 17Lands draft link",
				body: 'Paste the link from your 17Lands draft page (it looks like 17lands.com/data/draft?draft_id=…), or just the 32-character draft ID.',
				retryable: false
			};
		case 'draft_not_found':
			return {
				title: "We can't find that draft",
				body: 'It may be private, or the link may be wrong. In 17Lands, make sure the draft is shared publicly, then submit its link again.',
				retryable: false
			};
		case 'unsupported_set':
			return {
				title: "We don't cover that set yet",
				body: 'BoosterTutor launches with a single set and adds more later. This draft is from a set we have no statistics for yet.',
				retryable: false
			};
		case 'unsupported_format':
			return {
				title: "We don't cover that draft format",
				body: err.message,
				retryable: false
			};
		case 'unresolved_cards':
		case 'malformed_draft':
			return {
				title: "We couldn't read that draft",
				body: 'The draft data from 17Lands was incomplete or had cards we do not recognise, so we cannot grade it.',
				retryable: false
			};
		case 'upstream_failure':
			return {
				title: '17Lands is not answering',
				body: 'Their site had a problem just now. Nothing is wrong with your link, so try again in a minute.',
				retryable: true
			};
		case 'rate_limited': {
			const wait = err.retryAfter ? ` Try again in about ${formatWait(err.retryAfter)}.` : '';
			return {
				title: 'Slow down a little',
				body: `To be kind to 17Lands, we only fetch a few new drafts at a time.${wait}`,
				retryable: true
			};
		}
		case 'format_not_ready':
			return {
				title: 'Statistics for this format are not ready',
				body: 'We have not loaded this format’s win rates yet. Please check back later.',
				retryable: true
			};
		case 'network':
			return {
				title: "Can't reach BoosterTutor",
				body: 'Check your connection and try again. If it keeps happening, our server may be restarting.',
				retryable: true
			};
		default:
			return {
				title: 'Something went wrong',
				body: 'An unexpected error happened. Please try again.',
				retryable: true
			};
	}
}

function formatWait(seconds: number): string {
	return seconds < 90 ? `${Math.ceil(seconds)} seconds` : `${Math.ceil(seconds / 60)} minutes`;
}
