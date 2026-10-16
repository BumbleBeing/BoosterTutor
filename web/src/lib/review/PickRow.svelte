<script lang="ts">
	import { slide } from 'svelte/transition';
	import type { DraftReview } from '$lib/api/types';
	import Chip from '$lib/ui/Chip.svelte';
	import Panel from '$lib/ui/Panel.svelte';
	import {
		VERDICT_LABEL,
		formatFitness,
		formatWinRate,
		packLabel,
		type TimelinePick
	} from './model';

	let {
		entry,
		review,
		open = false,
		ontoggle
	}: {
		entry: TimelinePick;
		review: DraftReview;
		open?: boolean;
		ontoggle: () => void;
	} = $props();

	const pick = $derived(entry.pick);
	const takenName = $derived(entry.taken?.name ?? 'Unknown card');
	// Marker panel state is local: opening a note is separate from expanding the pick.
	let noteOpen = $state(false);
	const bestAlt = $derived(entry.alternatives[0]);
</script>

<Panel as="li" padded={false} id="pick-{entry.index}">
	<div class="flex items-stretch">
		<!-- data-pick-toggle lets the timeline's arrow-key handler find every row. -->
		<button
			type="button"
			data-pick-toggle
			aria-expanded={open}
			aria-controls="pick-detail-{entry.index}"
			onclick={ontoggle}
			class="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-page"
		>
			<span class="w-9 shrink-0 text-xs text-muted tabular-nums">
				<span class="sr-only">{packLabel(pick)}:</span>
				<span aria-hidden="true">p{pick.pick_number}</span>
			</span>
			<span class="min-w-0 flex-1">
				<span class="block font-medium sm:truncate">{takenName}</span>
				{#if bestAlt && pick.verdict !== 'solid'}
					<!-- Alternatives are ranked by fitness, so fitness is the number that
					     says why one is better. GIH WR is there for context only: a
					     "better" card can have the lower win rate if it suits the pool. -->
					<span class="block text-xs text-muted sm:truncate">
						Better: {bestAlt.info?.name ?? 'another card'}
						· fitness
						<span class="tabular-nums"
							>{formatFitness(bestAlt.score.total)} vs {formatFitness(
								entry.takenScore?.total
							)}</span
						>
						· GIH WR <span class="tabular-nums">{formatWinRate(bestAlt.score.gih_wr)}</span>
					</span>
				{/if}
			</span>
			<Chip tone={pick.verdict} data-verdict={pick.verdict}>{VERDICT_LABEL[pick.verdict]}</Chip>
		</button>
		{#if pick.noted}
			<button
				type="button"
				aria-expanded={noteOpen}
				aria-controls="pick-note-{entry.index}"
				aria-label="Coach's note for {packLabel(pick)}"
				onclick={() => (noteOpen = !noteOpen)}
				class="px-3 text-muted hover:text-accent"
			>
				<!-- A speech bubble. Filled when its panel is open. -->
				<svg viewBox="0 0 24 24" class="h-6 w-6" aria-hidden="true">
					<path
						d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4v-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"
						fill={noteOpen ? 'currentColor' : 'none'}
						stroke="currentColor"
						stroke-width="1.8"
						stroke-linejoin="round"
					/>
				</svg>
			</button>
		{/if}
	</div>

	{#if noteOpen}
		<!-- In 5b nobody sees prose: no Claude call is made from this page. -->
		<p
			id="pick-note-{entry.index}"
			class="mx-3 mb-3 rounded-md border border-periwinkle-line bg-periwinkle p-3 text-sm text-periwinkle-ink"
		>
			Sign in for a coach's note on this pick.
		</p>
	{/if}

	{#if open}
		<div id="pick-detail-{entry.index}" class="border-t border-line p-3" transition:slide>
			{#if entry.alternatives.length}
				<table class="w-full text-sm">
					<caption class="text-left font-display text-base font-semibold"
						>Cards with a higher fitness</caption
					>
					<thead class="text-xs text-muted">
						<tr>
							<th scope="col" class="py-1 text-left font-normal">Card</th>
							<th scope="col" class="py-1 text-right font-normal">Fitness</th>
							<th scope="col" class="py-1 pl-3 text-right font-normal">GIH WR</th>
						</tr>
					</thead>
					<tbody class="tabular-nums">
						{#each entry.alternatives as alt (alt.score.oracle_id)}
							<tr>
								<td class="max-w-0 truncate py-0.5">{alt.info?.name ?? 'Unknown card'}</td>
								<td class="py-0.5 text-right">{formatFitness(alt.score.total)}</td>
								<td class="py-0.5 pl-3 text-right text-muted">{formatWinRate(alt.score.gih_wr)}</td>
							</tr>
						{/each}
						<tr class="border-t border-line font-medium">
							<td class="max-w-0 truncate py-0.5">Your pick: {takenName}</td>
							<td class="py-0.5 text-right">{formatFitness(entry.takenScore?.total)}</td>
							<td class="py-0.5 pl-3 text-right text-muted"
								>{formatWinRate(entry.takenScore?.gih_wr)}</td
							>
						</tr>
					</tbody>
				</table>
			{:else}
				<p class="text-sm text-muted">Nothing in this pack had a higher fitness than your pick.</p>
			{/if}

			<h3 class="mt-4 text-base font-semibold">The pack ({pick.cards.length} different cards)</h3>
			<!-- Images exist only while this is open, so a collapsed draft loads none of them. -->
			<ul class="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5">
				{#each pick.cards as card (card.oracle_id)}
					{@const info = review.cards[card.oracle_id]}
					{@const taken = card.oracle_id === pick.picked}
					<li class="text-xs">
						{#if info?.image_normal}
							<img
								src={info.image_normal}
								alt={info.name}
								loading="lazy"
								width="488"
								height="680"
								class="h-auto w-full rounded-lg {taken
									? 'ring-4 ring-accent ring-offset-1 ring-offset-surface'
									: ''}"
							/>
						{:else}
							<div
								class="flex aspect-[488/680] items-center justify-center rounded-lg bg-sunken p-1 text-center"
							>
								{info?.name ?? 'Unknown card'}
							</div>
						{/if}
						<p class="mt-1 truncate font-medium">{info?.name ?? 'Unknown card'}</p>
						<p class="tabular-nums">Fitness {formatFitness(card.total)}</p>
						<p class="text-muted tabular-nums">GIH WR {formatWinRate(card.gih_wr)}</p>
						{#if card.fitness_class}
							<Chip tone={card.fitness_class} size="xs" class="mt-0.5"
								>{VERDICT_LABEL[card.fitness_class]}</Chip
							>
						{/if}
						{#if taken}<p class="font-semibold text-accent">Your pick</p>{/if}
						{#if card.insufficient_data}<p class="text-muted">few games</p>{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</Panel>
