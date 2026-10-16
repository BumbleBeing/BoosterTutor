// The admin page's coach, with `fetch` replaced: no server, no Claude.
import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { CoachNote, PickAnalysis } from '$lib/api/types';
import { fixtureReview } from '$lib/review/fixture';
import PickNotePanel from './PickNotePanel.svelte';
import { COACH_CONTEXT, Coach, pickNumberInDraft } from './coach.svelte';

const KEY = 'test-admin-key';

function note(pick: PickAnalysis, overrides: Partial<CoachNote> = {}): CoachNote {
	return {
		pack_number: pick.pack_number,
		pick_number: pick.pick_number,
		kind: 'critical',
		note: 'You passed the better card here.',
		prompt_version: 'pick_note.v1',
		model: 'claude-haiku-5-5',
		stats_snapshot: '2026-10-01',
		stale: false,
		...overrides
	};
}

/** Answer every request with `body` and `status`, and record what was asked. */
function fakeFetch(body: unknown, status = 200) {
	const calls: { url: string; init?: RequestInit }[] = [];
	vi.stubGlobal(
		'fetch',
		vi.fn(async (url: string, init?: RequestInit) => {
			calls.push({ url, init });
			return new Response(JSON.stringify(body), { status });
		})
	);
	return calls;
}

const notedPick = fixtureReview.analysis.picks.find((p) => p.noted)!;

afterEach(() => vi.unstubAllGlobals());

describe('pickNumberInDraft', () => {
	it('counts from 1 across packs', () => {
		expect(pickNumberInDraft({ pack_number: 1, pick_number: 1 }, 14)).toBe(1);
		expect(pickNumberInDraft({ pack_number: 2, pick_number: 7 }, 14)).toBe(21);
	});
});

describe('Coach', () => {
	it('asks for a note once, with the admin key, and keeps it', async () => {
		const calls = fakeFetch(note(notedPick));
		const coach = new Coach(fixtureReview.draft_id, fixtureReview.pack_size, KEY);
		await coach.writeNote(notedPick);
		await coach.writeNote(notedPick);

		expect(calls).toHaveLength(1);
		const n = pickNumberInDraft(notedPick, fixtureReview.pack_size);
		expect(calls[0].url).toMatch(new RegExp(`/picks/${n}/note$`));
		expect((calls[0].init?.headers as Record<string, string>)['X-Admin-Key']).toBe(KEY);
		const state = coach.noteFor(notedPick);
		expect(state.status === 'written' && state.note.note).toBe('You passed the better card here.');
	});

	it('remembers a failure so the panel can offer a retry', async () => {
		fakeFetch({ detail: { kind: 'prose_failed', message: 'no' } }, 502);
		const coach = new Coach(fixtureReview.draft_id, fixtureReview.pack_size, KEY);
		await coach.writeNote(notedPick);
		const state = coach.noteFor(notedPick);
		expect(state.status === 'failed' && state.error.kind).toBe('prose_failed');
	});
});

describe('PickNotePanel', () => {
	it('shows the sign-in prompt and asks for nothing without a coach', async () => {
		const calls = fakeFetch({});
		render(PickNotePanel, { pick: notedPick, id: 'n' });
		await expect.element(page.getByText("Sign in for a coach's note on this pick.")).toBeVisible();
		expect(calls).toHaveLength(0);
	});

	it('writes the note when opened, and tags one from older statistics', async () => {
		fakeFetch(note(notedPick, { stale: true }));
		const coach = new Coach(fixtureReview.draft_id, fixtureReview.pack_size, KEY);
		render(PickNotePanel, {
			props: { pick: notedPick, id: 'n' },
			context: new Map([[COACH_CONTEXT, coach]])
		});
		await expect.element(page.getByText('You passed the better card here.')).toBeVisible();
		await expect.element(page.getByText('Written against older stats')).toBeVisible();
	});
});
