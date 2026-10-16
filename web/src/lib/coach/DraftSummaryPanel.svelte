<script lang="ts">
	// The Draft Summary (ADR 0030): Claude's three short sections, and the Key
	// Picks it points to, named from the review so the card is Python's fact.
	import type { CoachSummary, DraftReview } from '$lib/api/types';
	import Chip from '$lib/ui/Chip.svelte';
	import Panel from '$lib/ui/Panel.svelte';
	import { pickNumberInDraft } from './coach.svelte';

	let { summary, review }: { summary: CoachSummary; review: DraftReview } = $props();

	function takenName(pack: number, pickNumber: number): string {
		const pick = review.analysis.picks.find(
			(p) => p.pack_number === pack && p.pick_number === pickNumber
		);
		return (pick && review.cards[pick.picked]?.name) ?? 'Unknown card';
	}
</script>

<Panel as="aside" aria-labelledby="summary-heading">
	<div class="flex flex-wrap items-baseline gap-2">
		<h3 id="summary-heading" class="text-lg font-semibold">Draft Summary</h3>
		{#if summary.stale}
			<Chip tone="questionable" size="xs">Written against older stats</Chip>
		{/if}
	</div>
	<dl class="mt-2 space-y-3 text-sm">
		<div>
			<dt class="font-semibold">The draft</dt>
			<dd class="mt-0.5">{summary.draft_arc}</dd>
		</div>
		<div>
			<dt class="font-semibold">The deck</dt>
			<dd class="mt-0.5">{summary.deck}</dd>
		</div>
		<div>
			<dt class="font-semibold">The lesson</dt>
			<dd class="mt-0.5">{summary.lesson}</dd>
		</div>
		{#if summary.key_picks.length}
			<div>
				<dt class="font-semibold">Key picks</dt>
				<dd class="mt-0.5">
					<ul>
						{#each summary.key_picks as key (`${key.pack_number}-${key.pick_number}`)}
							<li>
								<a
									class="text-accent underline"
									href="#pick-{pickNumberInDraft(key, review.pack_size) - 1}"
									>Pack {key.pack_number}, pick {key.pick_number}</a
								>: {takenName(key.pack_number, key.pick_number)}
							</li>
						{/each}
					</ul>
				</dd>
			</div>
		{/if}
	</dl>
</Panel>
