// Pure helpers for the review page: no network, no DOM, so they are easy to test.

import type { ApiError } from '$lib/api/client';
import type {
	CardInfo,
	CardScore,
	DraftReview,
	PickAnalysis,
	Verdict,
	WheelCard
} from '$lib/api/types';
import type { ManaColour } from '$lib/ui/tones';

/** The words on each verdict chip. Its colour comes from the chip's tone (lib/ui/tones.ts). */
export const VERDICT_LABEL: Record<Verdict, string> = {
	solid: 'Solid',
	questionable: 'Questionable',
	mistake: 'Mistake',
	indifferent: 'No real choice'
};

// Display order for the summary counts.
export const VERDICT_ORDER: Verdict[] = ['solid', 'questionable', 'mistake', 'indifferent'];

export interface TimelinePick {
	index: number; // 0-based position in the whole draft
	pick: PickAnalysis;
	taken: CardInfo | undefined;
	takenScore: CardScore | undefined;
	// Cards with a higher fitness than the one taken, best first (at most
	// three). Ranked by fitness (`score.total`), the number the verdict is
	// decided on, so the page must show that number beside them, not GIH WR.
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
		// The API sends cards best first already; sorting here keeps "ranked by
		// fitness" true even if that order ever changes.
		const alternatives = pick.cards
			.filter((c) => c.oracle_id !== pick.picked && c.scored && (c.total ?? -Infinity) > takenTotal)
			.sort((a, b) => (b.total ?? -Infinity) - (a.total ?? -Infinity))
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

/**
 * A fitness score, 57.84 -> "57.8". It is on the win-rate scale but is not a
 * win rate, so it gets no % sign: it is GIH WR adjusted for this pool.
 */
export function formatFitness(total: number | null | undefined): string {
	return total == null ? '—' : total.toFixed(1);
}

/** 2.345 -> "2.3 pp" (percentage points of fitness short of the best card). */
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

/**
 * 17Lands' event type in words: "PremierDraft" -> "Premier Draft". Open
 * drafts carry the set and a date ("OpenDraft_HOB_20261001"), which the page
 * already shows elsewhere, so only the format is kept.
 */
export function eventName(eventType: string): string {
	if (eventType === 'PremierDraft') return 'Premier Draft';
	if (eventType === 'TradDraft') return 'Traditional Draft';
	if (eventType.startsWith('OpenDraft')) return 'Open Draft';
	if (eventType === 'QuickDraft') return 'Quick Draft';
	// Anything else: drop a "_SUFFIX" and space out the words ("FooDraft" -> "Foo Draft").
	return eventType.split('_')[0].replace(/([a-z])([A-Z])/g, '$1 $2');
}

export function packLabel(pick: PickAnalysis): string {
	return `Pack ${pick.pack_number}, pick ${pick.pick_number}`;
}

// --- The wheel analysis --------------------------------------------------

export interface NamedWheelCard extends WheelCard {
	name: string;
}

export interface ColourRow {
	colour: ManaColour;
	name: string; // "Blue"
	good: number; // above-average cards of this colour that came back
	wheeled: number;
	taken: number; // taken by the other seven drafters
	best: NamedWheelCard | null; // the best good card of this colour that came back
}

export interface WheelLapView {
	from: number; // the pick the pack was first seen at
	to: number; // the pick it came back at
	wheeled: NamedWheelCard[]; // best GIH WR first
	taken: NamedWheelCard[]; // best GIH WR first
}

export interface WheelPackView {
	pack: number;
	colours: ColourRow[];
	laps: WheelLapView[];
}

/** Best GIH WR first; cards with no win rate last. */
function byWinRate(a: WheelCard, b: WheelCard): number {
	return (b.gih_wr ?? -Infinity) - (a.gih_wr ?? -Infinity);
}

/** The wheel analysis with card names joined on, ready to list. */
export function buildWheels(review: DraftReview): WheelPackView[] {
	const name = (id: string) => review.cards[id]?.name ?? 'Unknown card';
	const named = (c: WheelCard): NamedWheelCard => ({ ...c, name: name(c.oracle_id) });
	return review.analysis.wheels.map((wheel) => {
		// Find the full card behind `best_wheeled`, for its win rate.
		const everyWheeled = wheel.laps.flatMap((lap) => lap.wheeled);
		return {
			pack: wheel.pack_number,
			colours: wheel.colors.map((c) => {
				const best = everyWheeled.find((w) => w.oracle_id === c.best_wheeled);
				return {
					colour: c.color as ManaColour,
					name: COLOR_NAMES[c.color] ?? c.color,
					good: c.good_cards_wheeled,
					wheeled: c.cards_wheeled,
					taken: c.cards_taken_by_table,
					best: best ? named(best) : null
				};
			}),
			laps: wheel.laps.map((lap) => ({
				from: lap.first_pick,
				to: lap.returned_at,
				wheeled: lap.wheeled.map(named).sort(byWinRate),
				taken: lap.taken_by_table.map(named).sort(byWinRate)
			}))
		};
	});
}

/**
 * One line to say before the details: which colours sent good cards back.
 * "Good" is the API's `above_average`: a GIH WR at or above the format's average.
 */
export function wheelHeadline(view: WheelPackView): string {
	const flowing = view.colours.filter((c) => c.good > 0).sort((a, b) => b.good - a.good);
	if (!flowing.length) return 'No above-average card came back.';
	const parts = flowing.map((c) => `${c.name} ${c.good}`);
	const list = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0];
	return `Good cards that came back: ${list}.`;
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
				title: "We can't grade that kind of draft",
				body: 'Pick-two drafts (two cards per pick) are a different game from the other formats, so BoosterTutor does not cover them. Premier, Traditional and Open drafts all work.',
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
