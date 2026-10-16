<script lang="ts">
	// What came back in one pack, and what the rest of the table took
	// (analysis/wheel.py). Facts for reading signals; they play no part in any
	// pick's fitness (ADR 0018). Closed by default, so it costs a glance.
	import Chip from '$lib/ui/Chip.svelte';
	import { manaTone } from '$lib/ui/tones';
	import { formatWinRate, wheelHeadline, type NamedWheelCard, type WheelPackView } from './model';

	let { wheel }: { wheel: WheelPackView } = $props();
</script>

{#snippet cardList(cards: NamedWheelCard[])}
	<!-- Above-average cards are in bold ink; the rest are muted. -->
	<ul class="flex flex-wrap gap-x-3 gap-y-0.5">
		{#each cards as card, i (i)}
			<li class={card.above_average ? 'font-semibold text-ink' : 'text-muted'}>
				{card.name}
				<span class="font-normal tabular-nums">{formatWinRate(card.gih_wr)}</span>
			</li>
		{/each}
	</ul>
{/snippet}

<!-- <details> opens and closes itself, with the keyboard too, and needs no script. -->
<details class="group rounded-lg border border-line bg-surface shadow-sm">
	<summary
		class="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 rounded-lg px-4 py-3 hover:bg-page [&::-webkit-details-marker]:hidden"
	>
		<span class="font-display text-lg font-semibold">
			<span
				aria-hidden="true"
				class="inline-block text-muted transition-transform group-open:rotate-90">▸</span
			>
			What wheeled in pack {wheel.pack}
		</span>
		<span class="text-sm text-muted">{wheelHeadline(wheel)}</span>
	</summary>

	<div class="space-y-5 border-t border-line p-4 text-sm">
		<p class="text-muted">
			The packs of your first {wheel.laps.length} picks went round the other seven drafters and came back
			eight picks later. A good card coming back, one with a GIH WR at or above the format's average,
			says nobody else was taking its colour. Good cards are in bold.
		</p>

		<div>
			<h3 class="text-base font-semibold">By colour</h3>
			<ul class="mt-2 space-y-1.5">
				{#each wheel.colours as row (row.colour)}
					<li class="flex items-start gap-2">
						<Chip tone={manaTone(row.colour)} shape="square" size="xs" aria-hidden="true"
							>{row.colour}</Chip
						>
						<span>
							<span class="font-medium">{row.name}:</span>
							<span class="tabular-nums">{row.good}</span> good of
							<span class="tabular-nums">{row.wheeled}</span> that came back; the table took
							<span class="tabular-nums">{row.taken}</span>.
							{#if row.best}
								Best back: <span class="font-semibold">{row.best.name}</span>
								<span class="tabular-nums">({formatWinRate(row.best.gih_wr)})</span>.
							{/if}
						</span>
					</li>
				{/each}
			</ul>
			<p class="mt-1 text-xs text-muted">A gold card counts for each of its colours.</p>
		</div>

		<div>
			<h3 class="text-base font-semibold">Pick by pick</h3>
			<ol class="mt-2 space-y-3">
				{#each wheel.laps as lap (lap.from)}
					<li>
						<p class="font-medium">Pick {lap.from} → pick {lap.to}</p>
						<div class="mt-1 grid gap-1 sm:grid-cols-[7rem_1fr]">
							<span class="text-muted">Came back</span>
							{@render cardList(lap.wheeled)}
							<span class="text-muted">Table took</span>
							{@render cardList(lap.taken)}
						</div>
					</li>
				{/each}
			</ol>
		</div>
	</div>
</details>
