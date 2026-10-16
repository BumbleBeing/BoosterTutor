<script lang="ts">
	import type { DraftReview } from '$lib/api/types';
	import Chip from '$lib/ui/Chip.svelte';
	import Panel from '$lib/ui/Panel.svelte';
	import {
		VERDICT_LABEL,
		VERDICT_ORDER,
		archetypeName,
		eventName,
		finalArchetype,
		formatRecord
	} from './model';

	let { review }: { review: DraftReview } = $props();

	const archetype = $derived(archetypeName(finalArchetype(review)));
	const record = $derived(formatRecord(review));
	const picks = $derived(review.analysis.picks.length);
</script>

<Panel as="section" aria-label="Draft summary">
	<h1 class="text-3xl font-semibold">
		{review.set_code.toUpperCase()}
		<span class="font-normal text-muted">{eventName(review.event_type)}</span>
	</h1>
	<dl class="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:flex sm:flex-wrap">
		<div>
			<dt class="text-muted">Archetype</dt>
			<dd class="font-medium">{archetype ?? 'Undecided'}</dd>
		</div>
		<div>
			<dt class="text-muted">Record</dt>
			<dd class="font-medium">{record ?? 'Not known'}</dd>
		</div>
		<div>
			<dt class="text-muted">Picks</dt>
			<dd class="font-medium">{picks}</dd>
		</div>
		<div>
			<dt class="text-muted">Win rates as of</dt>
			<dd class="font-medium">{review.analysis.stats_snapshot}</dd>
		</div>
	</dl>
	<ul class="mt-4 flex flex-wrap gap-x-4 gap-y-2" aria-label="Verdict counts">
		{#each VERDICT_ORDER as verdict (verdict)}
			<li class="flex items-center gap-1.5 text-sm">
				<Chip tone={verdict} data-verdict={verdict}>{VERDICT_LABEL[verdict]}</Chip>
				<span class="font-semibold tabular-nums">{review.verdict_counts[verdict] ?? 0}</span>
			</li>
		{/each}
	</ul>
	<p class="mt-3 text-sm text-muted">
		{review.noted_picks.length}
		{review.noted_picks.length === 1 ? 'pick is' : 'picks are'} worth a closer look (marked with a speech
		bubble).
	</p>
</Panel>
