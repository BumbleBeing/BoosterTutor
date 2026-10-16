<script lang="ts">
	// The admin review: the same page as /draft/<id>, plus Claude's prose
	// (ADR 0031 s2, s7). The Admin Key is typed in here, checked by asking the
	// server for this draft's stored prose, and kept in sessionStorage for this
	// tab only (lib/coach/adminKey.ts). The public /draft/<id> page never shows
	// prose: only this page puts a coach in context.
	//
	// Phase 6 replaces the key box with the signed-in user's session.
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError, fetchReview } from '$lib/api/client';
	import type { DraftReview } from '$lib/api/types';
	import { forgetAdminKey, loadAdminKey, saveAdminKey } from '$lib/coach/adminKey';
	import { Coach } from '$lib/coach/coach.svelte';
	import CoachScope from '$lib/coach/CoachScope.svelte';
	import DeckSection from '$lib/deck/DeckSection.svelte';
	import ErrorState from '$lib/review/ErrorState.svelte';
	import ReviewSkeleton from '$lib/review/ReviewSkeleton.svelte';
	import ReviewSummary from '$lib/review/ReviewSummary.svelte';
	import ReviewTimeline from '$lib/review/ReviewTimeline.svelte';
	import Button from '$lib/ui/Button.svelte';
	import Panel from '$lib/ui/Panel.svelte';

	const draftId = page.params.id ?? '';

	let review = $state<DraftReview | null>(null);
	let error = $state<ApiError | null>(null);
	// The coach exists once a key has been accepted.
	let coach = $state<Coach | null>(null);
	let keyInput = $state('');
	let keyError = $state<string | null>(null);
	let checking = $state(false);

	async function loadReview() {
		review = null;
		error = null;
		try {
			review = await fetchReview(draftId);
		} catch (err) {
			error = err instanceof ApiError ? err : new ApiError('unknown', String(err));
		}
	}

	/** Try a key: it is kept only if the server accepts it. */
	async function useKey(key: string) {
		if (!review) return;
		checking = true;
		keyError = null;
		const candidate = new Coach(draftId, review.pack_size, key);
		try {
			await candidate.load();
			saveAdminKey(key);
			coach = candidate;
		} catch (err) {
			forgetAdminKey();
			keyError =
				err instanceof ApiError && err.kind === 'not_authorised'
					? 'That admin key was not accepted.'
					: err instanceof ApiError
						? err.message
						: String(err);
		} finally {
			checking = false;
		}
	}

	function signOut() {
		forgetAdminKey();
		coach = null;
		keyInput = '';
	}

	function onsubmit(event: SubmitEvent) {
		event.preventDefault();
		const key = keyInput.trim();
		if (key) useKey(key);
	}

	onMount(async () => {
		await loadReview();
		const remembered = loadAdminKey();
		if (remembered) await useKey(remembered);
	});
</script>

<svelte:head>
	<title>Admin review — BoosterTutor</title>
	<!-- Nothing here is for search engines. -->
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="mx-auto max-w-6xl px-4 py-6 sm:py-10">
	<a
		href={resolve('/draft/[id]', { id: draftId })}
		class="text-sm text-accent underline hover:text-accent-hover"
		>← The public review of this draft</a
	>

	<div class="mx-auto mt-4 max-w-3xl">
		<Panel as="section" aria-labelledby="admin-heading">
			<h1 id="admin-heading" class="text-xl font-semibold">Admin review</h1>
			{#if coach}
				<p class="mt-1 text-sm text-muted">
					The coach is on. Opening a Noted Pick's note, or submitting the first deck, calls Claude
					and stores what it writes.
				</p>
				<Button variant="secondary" size="sm" class="mt-3" onclick={signOut}
					>Forget the admin key</Button
				>
			{:else}
				<form class="mt-2 flex flex-wrap items-end gap-3" {onsubmit}>
					<label class="flex min-w-0 flex-1 flex-col text-sm">
						Admin key
						<input
							type="password"
							autocomplete="off"
							bind:value={keyInput}
							class="mt-1 rounded-md border border-line-strong bg-surface px-3 py-2"
						/>
					</label>
					<Button type="submit" disabled={checking || !review || !keyInput.trim()}>
						{checking ? 'Checking…' : 'Use key'}
					</Button>
				</form>
				<p class="mt-2 text-xs text-muted">Kept in this tab only, and forgotten when it closes.</p>
				{#if keyError}
					<p role="alert" class="mt-2 text-sm text-danger-ink">{keyError}</p>
				{/if}
			{/if}
		</Panel>
	</div>

	<div class="mt-8">
		{#if error}
			<ErrorState {error} onretry={loadReview} />
		{:else if review}
			<!-- Keyed on the coach, so the timeline and deck section start again
			     with it in context once a key is accepted, and without it after
			     the key is forgotten. -->
			{#key coach}
				<CoachScope {coach}>
					<div class="mx-auto max-w-3xl">
						<ReviewSummary {review} />
						<div class="mt-8"><ReviewTimeline {review} /></div>
					</div>
					<div class="mt-12"><DeckSection {review} /></div>
				</CoachScope>
			{/key}
		{:else}
			<ReviewSkeleton />
		{/if}
	</div>
</main>
