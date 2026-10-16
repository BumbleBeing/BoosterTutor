// The shapes `GET /api/drafts/{id}` and `POST /api/drafts` return. They mirror
// the Pydantic models in api/src/boostertutor/schemas/ and routes/drafts.py;
// if one changes, change the other. Only the fields the page uses are listed.

export type FitnessClass = 'solid' | 'questionable' | 'mistake';
export type Verdict = 'indifferent' | FitnessClass;

export interface CardScore {
	oracle_id: string;
	scored: boolean;
	total: number | null;
	gih_wr: number | null; // percent, e.g. 56.3
	games: number;
	insufficient_data: boolean;
	fitness_class: FitnessClass | null;
}

export interface PickAnalysis {
	pack_number: number;
	pick_number: number;
	picked: string;
	verdict: Verdict;
	best: string | null;
	gap: number | null; // percentage points short of the best card
	narrow: boolean;
	noted: boolean;
	pool: { size: number; predicted_archetype: string | null };
	cards: CardScore[]; // one per distinct card in the pack, best first
}

export interface CardInfo {
	name: string;
	mana_cost: string | null;
	type_line: string;
	cmc: number;
	colors: string;
	rarity: string | null;
	image_normal: string | null;
	image_art_crop: string | null;
}

export interface DraftReview {
	draft_id: string;
	set_code: string;
	event_type: string;
	drafted_at: string | null;
	wins: number | null;
	losses: number | null;
	pack_size: number;
	analysis: {
		stats_snapshot: string;
		picks: PickAnalysis[];
	};
	verdict_counts: Record<string, number>;
	noted_picks: [number, number][];
	cards: Record<string, CardInfo>;
	// The set's own basic lands by colour letter (art for the deck builder).
	basic_lands: Record<string, CardInfo>;
}

export interface ImportResponse {
	draft_id: string;
	cached: boolean;
}

// The `kind` values the API puts in an error body, plus two the client adds
// itself: `network` (the request never got an answer) and `unknown`.
export type ErrorKind =
	| 'invalid_input'
	| 'draft_not_found'
	| 'unsupported_set'
	| 'unsupported_format'
	| 'unresolved_cards'
	| 'malformed_draft'
	| 'upstream_failure'
	| 'rate_limited'
	| 'format_not_ready'
	| 'invalid_deck'
	| 'network'
	| 'unknown';

// What `POST /api/drafts/{id}/deck` takes and returns (schemas/deck_submission.py).

export interface SubmittedDeck {
	cards: string[]; // pool cards played, one entry per copy; no basics
	basics: Record<string, number>; // "W" | "U" | "B" | "R" | "G" -> how many
}

export type Grade = 'A' | 'B' | 'C' | 'D' | 'F';

export interface MetricRating {
	metric: string;
	value: number;
	percentile: number | null;
	grade: Grade | null;
}

export interface DeckRatings {
	rated: boolean;
	message: string | null; // "not enough data to rate" when unrated
	metrics: MetricRating[];
	predicted_win_rate: number | null; // percent
	percentile: number | null;
	grade: Grade | null;
}

export interface DeckMetrics {
	card_quality: number;
	curve: Record<string, number>; // mana value 1-6 -> nonland cards
	curve_distance: number;
	synergy: number;
	creatures: number;
	removal: number;
	mana_shortfall: number;
	mana_short_spell: string | null;
	mana_short_colors: string | null;
	mana_required: number | null;
	mana_available: number | null;
	spells_short: number;
	average_mana_value: number;
	effective_lands: number;
	land_target: number;
	land_distance: number;
	notable_omission: {
		oracle_id: string;
		gih_wr: number;
		instead_of: string;
		instead_of_gih_wr: number;
		gap: number;
	} | null;
}

export interface DeckReview {
	ratings: DeckRatings;
	metrics: DeckMetrics;
	colour_sources: Record<string, number>; // only colours the deck's spells use
	cards: Record<string, CardInfo>;
}
