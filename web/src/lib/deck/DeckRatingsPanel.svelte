<script lang="ts">
	import type { DeckReview } from '$lib/api/types';
	import Chip from '$lib/ui/Chip.svelte';
	import Panel from '$lib/ui/Panel.svelte';
	import { gradeTone } from '$lib/ui/tones';
	import { metricLabel, metricSays, omissionLine, shortSpellLine, sourcesLine } from './ratings';

	let { review }: { review: DeckReview } = $props();

	const m = $derived(review.metrics);
	const shortSpell = $derived(shortSpellLine(m, review));
	const omission = $derived(omissionLine(m, review));
</script>

<Panel as="section" aria-label="Deck Ratings">
	<h3 class="text-2xl font-semibold">Deck Ratings</h3>

	{#if review.ratings.rated && review.ratings.grade}
		<div class="mt-3 flex items-center gap-4">
			<Chip
				tone={gradeTone(review.ratings.grade)}
				shape="square"
				size="lg"
				data-overall-grade={review.ratings.grade}
				aria-label="Overall grade {review.ratings.grade}">{review.ratings.grade}</Chip
			>
			<p class="text-sm">
				Predicted win rate
				<strong class="tabular-nums">{review.ratings.predicted_win_rate?.toFixed(1)}%</strong>,
				better than <strong>{review.ratings.percentile}%</strong> of 17Lands decks in this format. A C
				is an average 17Lands deck.
			</p>
		</div>
		<ul class="mt-4 divide-y divide-line text-sm">
			{#each review.ratings.metrics as metric (metric.metric)}
				<li class="flex items-center gap-3 py-2">
					{#if metric.grade}
						<Chip tone={gradeTone(metric.grade)} shape="square" aria-label="Grade {metric.grade}"
							>{metric.grade}</Chip
						>
					{:else}
						<!-- No grade for this metric: keep the column lined up. -->
						<span class="h-7 w-7 shrink-0"></span>
					{/if}
					<span class="w-32 shrink-0 font-medium">{metricLabel(metric)}</span>
					<span class="text-muted">{metricSays(metric)}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="mt-3 text-sm">Not enough data to rate this format yet. The facts below still hold.</p>
	{/if}

	<dl class="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
		<div>
			<dt class="text-muted">Lands</dt>
			<dd class="font-medium tabular-nums" data-effective-lands>
				{m.effective_lands.toFixed(1)} effective, target {m.land_target}
			</dd>
		</div>
		<div>
			<dt class="text-muted">Colour sources</dt>
			<dd class="font-medium" data-colour-sources>
				{sourcesLine(review.colour_sources) || 'No coloured spells'}
			</dd>
		</div>
	</dl>
	{#if shortSpell}<p class="mt-3 text-sm text-warning-ink">{shortSpell}</p>{/if}
	{#if omission}<p class="mt-2 text-sm">{omission}</p>{/if}
</Panel>
