// The coach on the admin page: Claude's Pick Notes and Draft Summary for one
// draft, and the Admin Key that unlocks them (ADR 0031 s2).
//
// The admin page puts a `Coach` in Svelte context with `provideCoach`. The
// review components look for one with `useCoach`: when there is none, as on
// the shareable /draft/<id> page, they show "Sign in for a coach's note" and
// never ask for prose. So the public page can't show admin-written prose
// even by accident: it has no coach to ask.

import { getContext, setContext } from 'svelte';
import { ApiError, fetchCoachReview, submitCoachedDeck, writePickNote } from '$lib/api/client';
import type {
	CoachedDeckReview,
	CoachNote,
	CoachSummary,
	PickAnalysis,
	SubmittedDeck
} from '$lib/api/types';

// Exported for tests, which put a coach in context without a page.
export const COACH_CONTEXT = Symbol('coach');

/** "1-12" for P1p12: how notes are keyed. */
export function pickKey(pick: Pick<PickAnalysis, 'pack_number' | 'pick_number'>): string {
	return `${pick.pack_number}-${pick.pick_number}`;
}

/** The pick's place in the draft, as the note endpoint wants it: 1 is P1p1. */
export function pickNumberInDraft(
	pick: Pick<PickAnalysis, 'pack_number' | 'pick_number'>,
	packSize: number
): number {
	return (pick.pack_number - 1) * packSize + pick.pick_number;
}

export type NoteState =
	| { status: 'idle' }
	| { status: 'writing' }
	| { status: 'written'; note: CoachNote }
	| { status: 'failed'; error: ApiError };

export class Coach {
	// Stored notes, by `pickKey`. Replaced, not mutated, so Svelte sees changes.
	notes = $state<Record<string, NoteState>>({});
	summary = $state<CoachSummary | null>(null);

	constructor(
		readonly draftId: string,
		readonly packSize: number,
		readonly adminKey: string
	) {}

	/** Fetch what is already stored. Throws an ApiError, e.g. a wrong key. */
	async load(): Promise<void> {
		const stored = await fetchCoachReview(this.draftId, this.adminKey);
		this.notes = Object.fromEntries(
			stored.notes.map((note) => [pickKey(note), { status: 'written', note } as NoteState])
		);
		this.summary = stored.summary;
	}

	noteFor(pick: PickAnalysis): NoteState {
		return this.notes[pickKey(pick)] ?? { status: 'idle' };
	}

	/**
	 * The note for a Noted Pick: stored already, or written now by Claude (a
	 * few seconds). Does nothing while a note is written or once it exists.
	 */
	async writeNote(pick: PickAnalysis): Promise<void> {
		const current = this.noteFor(pick).status;
		if (current === 'writing' || current === 'written') return;
		const key = pickKey(pick);
		this.notes = { ...this.notes, [key]: { status: 'writing' } };
		let next: NoteState;
		try {
			const n = pickNumberInDraft(pick, this.packSize);
			next = { status: 'written', note: await writePickNote(this.draftId, n, this.adminKey) };
		} catch (err) {
			next = {
				status: 'failed',
				error: err instanceof ApiError ? err : new ApiError('unknown', String(err))
			};
		}
		this.notes = { ...this.notes, [key]: next };
	}

	/** Submit a deck with the key: stored, and the first one gets a Draft Summary. */
	async submitDeck(deck: SubmittedDeck): Promise<CoachedDeckReview> {
		const reviewed = await submitCoachedDeck(this.draftId, deck, this.adminKey);
		if (reviewed.summary) this.summary = reviewed.summary;
		return reviewed;
	}
}

export function provideCoach(coach: Coach): void {
	setContext(COACH_CONTEXT, coach);
}

/** The page's coach, or undefined on a page without one (the public review). */
export function useCoach(): Coach | undefined {
	return getContext<Coach | undefined>(COACH_CONTEXT);
}
