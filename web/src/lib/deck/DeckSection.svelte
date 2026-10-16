<script lang="ts">
	// The deck builder on the review page: builds the pool from the review,
	// sends the deck to the server and shows the Deck Ratings that come back.
	//
	// On the admin page a coach is in context (lib/coach): the deck is sent
	// with the Admin Key, and the Draft Summary shows where everyone else is
	// asked to sign in.
	import { ApiError, submitDeck } from '$lib/api/client';
	import type { DeckReview, DraftReview, ProseUnavailable } from '$lib/api/types';
	import { useCoach } from '$lib/coach/coach.svelte';
	import DraftSummaryPanel from '$lib/coach/DraftSummaryPanel.svelte';
	import DeckBuilder from './DeckBuilder.svelte';
	import DeckRatingsPanel from './DeckRatingsPanel.svelte';
	import { poolFromReview } from './pool';

	let { review }: { review: DraftReview } = $props();

	const pool = $derived(poolFromReview(review));
	const basicImages = $derived(
		Object.fromEntries(
			Object.entries(review.basic_lands).map(([c, info]) => [c, info.image_normal])
		)
	);

	const coach = useCoach();

	let ratings = $state<DeckReview | null>(null);
	let summaryUnavailable = $state<ProseUnavailable | null>(null);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	async function onSubmit(deck: Parameters<typeof submitDeck>[1]) {
		submitting = true;
		error = null;
		try {
			// A new submission replaces the ratings of the one before it.
			if (coach) {
				const coached = await coach.submitDeck(deck);
				summaryUnavailable = coached.summary_unavailable;
				ratings = coached;
			} else {
				ratings = await submitDeck(review.draft_id, deck);
			}
		} catch (err) {
			error = err instanceof ApiError ? err.message : String(err);
		} finally {
			submitting = false;
		}
	}
</script>

<section aria-labelledby="deck-heading" class="border-t border-line pt-8">
	<h2 id="deck-heading" class="text-3xl font-semibold">
		Submit your final deck for a full Draft Review
	</h2>
	<div class="mt-4">
		<DeckBuilder
			{pool}
			{basicImages}
			{onSubmit}
			{submitting}
			confirmMessage={coach
				? coach.summary
					? 'Submit this deck for ratings? It is saved as your current deck; the Draft Summary stays about the first one.'
					: 'Submit this deck? It is saved, and Claude writes its Draft Summary (a few seconds, and a few cents).'
				: 'Submit this deck for ratings? Nothing is saved, and you can submit another build any time: each new one replaces the ratings below.'}
		/>
	</div>

	{#if error}
		<p
			role="alert"
			class="mt-4 rounded border border-danger-line bg-danger p-3 text-sm text-danger-ink"
		>
			{error}
		</p>
	{/if}

	{#if coach?.summary && !ratings}
		<!-- Written for an earlier visit's deck, and stored. -->
		<div class="mt-8"><DraftSummaryPanel summary={coach.summary} {review} /></div>
	{/if}

	{#if ratings}
		<div class="mt-8 space-y-4" aria-live="polite">
			<DeckRatingsPanel review={ratings} />
			{#if coach?.summary}
				<DraftSummaryPanel summary={coach.summary} {review} />
			{:else if coach && summaryUnavailable}
				<p
					role="alert"
					class="rounded border border-danger-line bg-danger p-3 text-sm text-danger-ink"
				>
					No Draft Summary this time: {summaryUnavailable.message} The next deck you submit tries again.
				</p>
			{:else if !coach}
				<!-- Claude's prose needs an account (ADR 0021). -->
				<aside class="rounded-lg border border-dashed border-line-strong p-4 text-sm text-muted">
					<h3 class="text-lg font-semibold text-ink">Draft Summary</h3>
					<p class="mt-1">Sign in for a Draft Summary</p>
				</aside>
			{/if}
		</div>
	{/if}
</section>
