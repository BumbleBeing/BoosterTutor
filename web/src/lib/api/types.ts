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
	| 'network'
	| 'unknown';
