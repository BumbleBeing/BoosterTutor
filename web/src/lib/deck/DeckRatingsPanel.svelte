<script lang="ts">
	import type { DeckReview } from '$lib/api/types';
	import {
		GRADE_STYLE,
		metricLabel,
		metricSays,
		omissionLine,
		shortSpellLine,
		sourcesLine
	} from './ratings';

	let { review }: { review: DeckReview } = $props();

	const m = $derived(review.metrics);
	const shortSpell = $derived(shortSpellLine(m, review));
	const omission = $derived(omissionLine(m, review));
</script>

<section aria-label="Deck Ratings" class="rounded-lg border border-slate-200 bg-white p-5">
	<h3 class="text-lg font-semibold">Deck Ratings</h3>

	{#if review.ratings.rated && review.ratings.grade}
		<div class="mt-3 flex items-center gap-4">
			<span
				class="inline-flex h-14 w-14 items-center justify-center rounded-lg text-3xl font-bold ring-1 ring-inset {GRADE_STYLE[
					review.ratings.grade
				]}"
				data-overall-grade={review.ratings.grade}
				aria-label="Overall grade {review.ratings.grade}">{review.ratings.grade}</span
			>
			<p class="text-sm text-slate-700">
				Predicted win rate
				<strong class="tabular-nums">{review.ratings.predicted_win_rate?.toFixed(1)}%</strong>,
				better than <strong>{review.ratings.percentile}%</strong> of 17Lands decks in this format. A C
				is an average 17Lands deck.
			</p>
		</div>
		<ul class="mt-4 divide-y divide-slate-100 text-sm">
			{#each review.ratings.metrics as metric (metric.metric)}
				<li class="flex items-center gap-3 py-2">
					<span
						class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded font-bold ring-1 ring-inset {metric.grade
							? GRADE_STYLE[metric.grade]
							: ''}"
						aria-label="Grade {metric.grade}">{metric.grade}</span
					>
					<span class="w-32 shrink-0 font-medium">{metricLabel(metric)}</span>
					<span class="text-slate-600">{metricSays(metric)}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="mt-3 text-sm text-slate-700">
			Not enough data to rate this format yet. The facts below still hold.
		</p>
	{/if}

	<dl class="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
		<div>
			<dt class="text-slate-500">Lands</dt>
			<dd class="font-medium tabular-nums" data-effective-lands>
				{m.effective_lands.toFixed(1)} effective, target {m.land_target}
			</dd>
		</div>
		<div>
			<dt class="text-slate-500">Colour sources</dt>
			<dd class="font-medium" data-colour-sources>
				{sourcesLine(review.colour_sources) || 'No coloured spells'}
			</dd>
		</div>
	</dl>
	{#if shortSpell}<p class="mt-3 text-sm text-amber-900">{shortSpell}</p>{/if}
	{#if omission}<p class="mt-2 text-sm text-slate-700">{omission}</p>{/if}
</section>
