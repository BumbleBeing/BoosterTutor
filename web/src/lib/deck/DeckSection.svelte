<script lang="ts">
	// The deck builder on the review page: builds the pool from the review,
	// sends the deck to the server and shows the Deck Ratings that come back.
	import { ApiError, submitDeck } from '$lib/api/client';
	import type { DeckReview, DraftReview } from '$lib/api/types';
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

	let ratings = $state<DeckReview | null>(null);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	async function onSubmit(deck: Parameters<typeof submitDeck>[1]) {
		submitting = true;
		error = null;
		try {
			// A new submission replaces the ratings of the one before it.
			ratings = await submitDeck(review.draft_id, deck);
		} catch (err) {
			error = err instanceof ApiError ? err.message : String(err);
		} finally {
			submitting = false;
		}
	}
</script>

<section aria-labelledby="deck-heading" class="border-t border-slate-200 pt-8">
	<h2 id="deck-heading" class="text-xl font-bold">
		Submit your final deck for a full Draft Review
	</h2>
	<div class="mt-4">
		<DeckBuilder
			{pool}
			{basicImages}
			{onSubmit}
			{submitting}
			confirmMessage="Submit this deck for ratings? Nothing is saved, and you can submit another build any time: each new one replaces the ratings below."
		/>
	</div>

	{#if error}
		<p role="alert" class="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">
			{error}
		</p>
	{/if}

	{#if ratings}
		<div class="mt-8 space-y-4" aria-live="polite">
			<DeckRatingsPanel review={ratings} />
			<!-- Where the Draft Summary will go; Claude's prose needs an account (ADR 0021). -->
			<aside class="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-600">
				<h3 class="font-semibold text-slate-800">Draft Summary</h3>
				<p class="mt-1">Sign in for a Draft Summary</p>
			</aside>
		</div>
	{/if}
</section>
