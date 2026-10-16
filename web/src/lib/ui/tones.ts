// Which token classes colour a chip. Each tone is a background, an ink and a
// ring, all defined in routes/layout.css. Tailwind only generates classes it
// can see written out in full, so every class name here is spelled out rather
// than built from pieces like `bg-${tone}`.

import type { Grade, Verdict } from '$lib/api/types';

export type ManaColour = 'W' | 'U' | 'B' | 'R' | 'G';

// A grade's tone is `grade-a` and a colour's is `mana-b`, so the grade B and
// the colour black never share a name.
export type Tone =
	Verdict | `grade-${Lowercase<Grade>}` | `mana-${Lowercase<ManaColour>}` | 'neutral';

export const TONE_CLASSES: Record<Tone, string> = {
	// Verdicts (ADR 0008)
	solid: 'bg-solid text-solid-ink ring-solid-ring',
	questionable: 'bg-questionable text-questionable-ink ring-questionable-ring',
	mistake: 'bg-mistake text-mistake-ink ring-mistake-ring',
	indifferent: 'bg-indifferent text-indifferent-ink ring-indifferent-ring',
	// Deck Ratings grades (ADR 0026)
	'grade-a': 'bg-grade-a text-grade-a-ink ring-grade-a-ring',
	'grade-b': 'bg-grade-b text-grade-b-ink ring-grade-b-ring',
	'grade-c': 'bg-grade-c text-grade-c-ink ring-grade-c-ring',
	'grade-d': 'bg-grade-d text-grade-d-ink ring-grade-d-ring',
	'grade-f': 'bg-grade-f text-grade-f-ink ring-grade-f-ring',
	// The five colours of Magic
	'mana-w': 'bg-mana-w text-mana-w-ink ring-mana-w-ring',
	'mana-u': 'bg-mana-u text-mana-u-ink ring-mana-u-ring',
	'mana-b': 'bg-mana-b text-mana-b-ink ring-mana-b-ring',
	'mana-r': 'bg-mana-r text-mana-r-ink ring-mana-r-ring',
	'mana-g': 'bg-mana-g text-mana-g-ink ring-mana-g-ring',
	neutral: 'bg-sunken text-ink ring-line'
};

export const gradeTone = (grade: Grade): Tone => `grade-${grade.toLowerCase() as Lowercase<Grade>}`;

/** A colour letter's tone; anything that isn't one of W, U, B, R, G is neutral. */
export function manaTone(colour: string): Tone {
	return 'WUBRG'.includes(colour) && colour.length === 1
		? `mana-${colour.toLowerCase() as Lowercase<ManaColour>}`
		: 'neutral';
}
