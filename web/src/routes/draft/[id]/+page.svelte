<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError, fetchReview } from '$lib/api/client';
	import type { DraftReview } from '$lib/api/types';
	import DeckSection from '$lib/deck/DeckSection.svelte';
	import ErrorState from '$lib/review/ErrorState.svelte';
	import ReviewSkeleton from '$lib/review/ReviewSkeleton.svelte';
	import ReviewSummary from '$lib/review/ReviewSummary.svelte';
	import ReviewTimeline from '$lib/review/ReviewTimeline.svelte';

	let review = $state<DraftReview | null>(null);
	let error = $state<ApiError | null>(null);

	async function load() {
		review = null;
		error = null;
		try {
			review = await fetchReview(page.params.id ?? '');
		} catch (err) {
			error = err instanceof ApiError ? err : new ApiError('unknown', String(err));
		}
	}

	// Fetch in the browser so the skeleton shows while the server computes verdicts.
	onMount(load);
</script>

<svelte:head><title>Draft review — BoosterTutor</title></svelte:head>

<!-- Wide enough for the deck builder's nine columns; the review itself stays narrow. -->
<main class="mx-auto max-w-6xl px-4 py-6 sm:py-10">
	<a href={resolve('/')} class="text-sm text-accent underline hover:text-accent-hover"
		>← Review another draft</a
	>
	<div class="mt-4">
		{#if error}
			<ErrorState {error} onretry={load} />
		{:else if review}
			<div class="mx-auto max-w-3xl">
				<ReviewSummary {review} />
				<div class="mt-8"><ReviewTimeline {review} /></div>
			</div>
			<div class="mt-12"><DeckSection {review} /></div>
		{:else}
			<ReviewSkeleton />
		{/if}
	</div>
</main>
