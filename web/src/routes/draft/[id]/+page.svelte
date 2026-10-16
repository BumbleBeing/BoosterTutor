<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError, fetchReview } from '$lib/api/client';
	import type { DraftReview } from '$lib/api/types';
	import ErrorState from '$lib/review/ErrorState.svelte';
	import ReviewSkeleton from '$lib/review/ReviewSkeleton.svelte';
	import ReviewSummary from '$lib/review/ReviewSummary.svelte';
	import ReviewTimeline from '$lib/review/ReviewTimeline.svelte';
	import SeventeenLandsCredit from '$lib/review/SeventeenLandsCredit.svelte';

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

<main class="mx-auto max-w-3xl px-4 py-6 sm:py-10">
	<a href={resolve('/')} class="text-sm text-slate-600 underline">← Review another draft</a>
	<div class="mt-4">
		{#if error}
			<ErrorState {error} onretry={load} />
		{:else if review}
			<ReviewSummary {review} />
			<div class="mt-8"><ReviewTimeline {review} /></div>
		{:else}
			<ReviewSkeleton />
		{/if}
	</div>
	<footer class="mt-12 border-t border-slate-200 pt-4"><SeventeenLandsCredit /></footer>
</main>
