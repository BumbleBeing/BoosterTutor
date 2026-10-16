<script lang="ts">
	import type { DraftReview } from '$lib/api/types';
	import PickRow from './PickRow.svelte';
	import { buildTimeline } from './model';

	let { review }: { review: DraftReview } = $props();

	const packs = $derived(buildTimeline(review));
	// Which picks are expanded, by draft index. A Set would not trigger updates
	// in Svelte 5 when mutated in place, so we replace it each time.
	let openPicks = $state<number[]>([]);

	function toggle(index: number) {
		openPicks = openPicks.includes(index)
			? openPicks.filter((i) => i !== index)
			: [...openPicks, index];
	}

	// Arrow keys / j / k move between picks; Home / End jump to the ends.
	// Enter and Space already expand a focused row because it is a real <button>.
	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (!target.matches('[data-pick-toggle]')) return;
		const rows = [...document.querySelectorAll<HTMLElement>('[data-pick-toggle]')];
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
<div {onkeydown} role="presentation" class="space-y-8">
	<p class="hidden text-xs text-slate-500 sm:block">
		Tip: use ↑ ↓ (or j / k) to move between picks, Enter to open one.
	</p>
	{#each packs as pack (pack.number)}
		<section aria-labelledby="pack-{pack.number}">
			<h2 id="pack-{pack.number}" class="mb-3 text-lg font-semibold">Pack {pack.number}</h2>
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
		</section>
	{/each}
</div>
