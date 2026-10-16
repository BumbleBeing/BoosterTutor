// Talks to the FastAPI backend. Every failure is turned into an `ApiError`
// whose `kind` the pages switch on, so no component parses HTTP by hand.

import { PUBLIC_API_URL } from '$env/static/public';
import type {
	CoachedDeckReview,
	CoachNote,
	CoachReview,
	DeckReview,
	DraftReview,
	ErrorKind,
	ImportResponse,
	SubmittedDeck
} from './types';

export class ApiError extends Error {
	kind: ErrorKind;
	// Seconds until the client may try again (rate limits only).
	retryAfter: number | null;

	constructor(kind: ErrorKind, message: string, retryAfter: number | null = null) {
		super(message);
		this.kind = kind;
		this.retryAfter = retryAfter;
	}
}

const KNOWN_KINDS: ErrorKind[] = [
	'invalid_input',
	'draft_not_found',
	'unsupported_set',
	'unsupported_format',
	'unresolved_cards',
	'malformed_draft',
	'upstream_failure',
	'rate_limited',
	'format_not_ready',
	'invalid_deck',
	'not_noted',
	'not_authorised',
	'coach_retired',
	'prose_failed'
];

/** Turn a non-2xx response into an ApiError. The API's body is `{detail: {kind, message}}`. */
export async function toApiError(res: Response): Promise<ApiError> {
	let kind: ErrorKind = 'unknown';
	let message = `The server answered ${res.status}.`;
	try {
		const body = await res.json();
		const detail = body?.detail;
		if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
			if (KNOWN_KINDS.includes(detail.kind)) kind = detail.kind;
			if (typeof detail.message === 'string') message = detail.message;
		} else if (res.status === 422) {
			// FastAPI's own validation error (e.g. a missing field), not ours.
			kind = 'invalid_input';
		}
	} catch {
		// Not JSON (a proxy's error page, say): keep the generic message.
	}
	const retry = Number(res.headers.get('Retry-After'));
	return new ApiError(kind, message, Number.isFinite(retry) && retry > 0 ? retry : null);
}

async function request<T>(fetchFn: typeof fetch, path: string, init?: RequestInit): Promise<T> {
	let res: Response;
	try {
		res = await fetchFn(`${PUBLIC_API_URL}${path}`, init);
	} catch {
		throw new ApiError('network', "Couldn't reach BoosterTutor's server.");
	}
	if (!res.ok) throw await toApiError(res);
	return (await res.json()) as T;
}

/** Submit a 17Lands link or draft id. Resolves with the id to open. */
export function importDraft(link: string, fetchFn: typeof fetch = fetch): Promise<ImportResponse> {
	return request<ImportResponse>(fetchFn, '/api/drafts', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ link })
	});
}

/** Load a draft's review. Verdicts are recomputed by the server on every call. */
export function fetchReview(id: string, fetchFn: typeof fetch = fetch): Promise<DraftReview> {
	return request<DraftReview>(fetchFn, `/api/drafts/${encodeURIComponent(id)}`);
}

/** Rate a 40-card deck built from a draft's pool. Nothing is stored server-side. */
export function submitDeck(
	id: string,
	deck: SubmittedDeck,
	fetchFn: typeof fetch = fetch
): Promise<DeckReview> {
	return request<DeckReview>(fetchFn, `/api/drafts/${encodeURIComponent(id)}/deck`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(deck)
	});
}

// --------------------------------------------------------------------------
// Claude's prose, with the Admin Key (ADR 0031 s2). Phase 6 swaps the key for
// the signed-in user's session; until then only the admin page calls these.
// --------------------------------------------------------------------------

function adminHeaders(adminKey: string): Record<string, string> {
	return { 'X-Admin-Key': adminKey };
}

/** Everything stored for this draft: its Pick Notes, Draft Summary and decks. No Claude call. */
export function fetchCoachReview(
	id: string,
	adminKey: string,
	fetchFn: typeof fetch = fetch
): Promise<CoachReview> {
	return request<CoachReview>(fetchFn, `/api/drafts/${encodeURIComponent(id)}/coach`, {
		headers: adminHeaders(adminKey)
	});
}

/**
 * The Pick Note for the draft's `n`th pick (1 is P1p1). The server returns the
 * stored note, or asks Claude for one (a few seconds) and stores it.
 */
export function writePickNote(
	id: string,
	n: number,
	adminKey: string,
	fetchFn: typeof fetch = fetch
): Promise<CoachNote> {
	return request<CoachNote>(fetchFn, `/api/drafts/${encodeURIComponent(id)}/picks/${n}/note`, {
		method: 'POST',
		headers: adminHeaders(adminKey)
	});
}

/** Rate a deck with the Admin Key: it is stored, and the first one gets a Draft Summary. */
export function submitCoachedDeck(
	id: string,
	deck: SubmittedDeck,
	adminKey: string,
	fetchFn: typeof fetch = fetch
): Promise<CoachedDeckReview> {
	return request<CoachedDeckReview>(fetchFn, `/api/drafts/${encodeURIComponent(id)}/deck`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...adminHeaders(adminKey) },
		body: JSON.stringify(deck)
	});
}
