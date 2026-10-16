<script lang="ts">
	import type { DraftReview } from '$lib/api/types';
	import PickRow from './PickRow.svelte';
	import WheelPanel from './WheelPanel.svelte';
	import { buildTimeline, buildWheels } from './model';

	let { review }: { review: DraftReview } = $props();

	const packs = $derived(buildTimeline(review));
	const wheels = $derived(buildWheels(review));
	// Which picks are expanded, by draft index. A Set would not trigger updates
	// in Svelte 5 when mutated in place, so we replace it each time.
	let openPicks = $state<number[]>([]);
	// This component's own outer element, so the key handler looks only at its
	// own rows and never at another timeline elsewhere on the page.
	let container = $state<HTMLDivElement | null>(null);

	function toggle(index: number) {
		openPicks = openPicks.includes(index)
			? openPicks.filter((i) => i !== index)
			: [...openPicks, index];
	}

	// Arrow keys / j / k move between picks; Home / End jump to the ends.
	// Enter and Space already expand a focused row because it is a real <button>.
	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (!container || !target.matches('[data-pick-toggle]')) return;
		const rows = [...container.querySelectorAll<HTMLElement>('[data-pick-toggle]')];
		const at = rows.indexOf(target);
		let next = -1;
		if (event.key === 'ArrowDown' || event.key === 'j') next = Math.min(at + 1, rows.length - 1);
		else if (event.key === 'ArrowUp' || event.key === 'k') next = Math.max(at - 1, 0);
		else if (event.key === 'Home') next = 0;
		else if (event.key === 'End') next = rows.length - 1;
		if (next < 0) return;
		event.preventDefault();
		rows[next].focus();
	}
</script>

<!-- Only listens for keys bubbling up from the row buttons inside. -->
<div bind:this={container} {onkeydown} role="presentation" class="space-y-8">
	<!-- What the numbers mean. Worded from ADRs 0008, 0012 and 0018 and
	     CONTEXT.md's "Fitness": no claim here that the server doesn't compute. -->
	<div class="space-y-2 text-sm text-muted">
		<p>
			Every pick is graded on <strong class="font-semibold text-ink">fitness</strong>: what a card
			was worth to your pool at that moment, in points of win rate. It starts from the card's
			17Lands GIH WR (how often decks win with it in hand), takes off a tax for colours your pool
			isn't in, and adjusts for your curve, removal and synergy. A pick within 2 points of the
			pack's best is Solid, within 4 is Questionable, and further is a Mistake. When every card was
			within 2, there was no real choice.
		</p>
		<p class="hidden text-xs sm:block">
			Tip: use ↑ ↓ (or j / k) to move between picks, Enter to open one.
		</p>
	</div>
	{#each packs as pack (pack.number)}
		{@const wheel = wheels.find((w) => w.pack === pack.number)}
		<section aria-labelledby="pack-{pack.number}">
			<h2 id="pack-{pack.number}" class="mb-3 text-2xl font-semibold">Pack {pack.number}</h2>
			<ol class="space-y-2">
				{#each pack.picks as entry (entry.index)}
					<PickRow
						{entry}
						{review}
						open={openPicks.includes(entry.index)}
						ontoggle={() => toggle(entry.index)}
					/>
				{/each}
			</ol>
			{#if wheel && wheel.laps.length}
				<div class="mt-3"><WheelPanel {wheel} /></div>
			{/if}
		</section>
	{/each}
</div>
