<script lang="ts">
	import { slide } from 'svelte/transition';
	import VerdictChip from './VerdictChip.svelte';
	import { VERDICT_STYLE, formatGap, formatWinRate, packLabel, type TimelinePick } from './model';
	import type { DraftReview } from '$lib/api/types';

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

<li class="rounded-lg border border-slate-200 bg-white" id="pick-{entry.index}">
	<div class="flex items-stretch">
		<!-- data-pick-toggle lets the timeline's arrow-key handler find every row. -->
		<button
			type="button"
			data-pick-toggle
			aria-expanded={open}
			aria-controls="pick-detail-{entry.index}"
			onclick={ontoggle}
			class="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-slate-50"
		>
			<span class="w-9 shrink-0 text-xs text-slate-500 tabular-nums">
				<span class="sr-only">{packLabel(pick)}:</span>
				<span aria-hidden="true">p{pick.pick_number}</span>
			</span>
			<span class="min-w-0 flex-1">
				<span class="block truncate font-medium">{takenName}</span>
				{#if bestAlt && pick.verdict !== 'solid'}
					<span class="block truncate text-xs text-slate-500">
						Better: {bestAlt.info?.name ?? 'another card'}
						({formatWinRate(bestAlt.score.gih_wr)} GIH WR)
						{#if pick.gap != null}· {formatGap(pick.gap)} short{/if}
					</span>
				{/if}
			</span>
			<VerdictChip verdict={pick.verdict} />
		</button>
		{#if pick.noted}
			<button
				type="button"
				aria-expanded={noteOpen}
				aria-controls="pick-note-{entry.index}"
				aria-label="Coach's note for {packLabel(pick)}"
				onclick={() => (noteOpen = !noteOpen)}
				class="px-3 text-slate-500 hover:text-slate-900"
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
		<p id="pick-note-{entry.index}" class="mx-3 mb-3 rounded-md bg-sky-50 p-3 text-sm text-sky-950">
			Sign in for a coach's note on this pick.
		</p>
	{/if}

	{#if open}
		<div id="pick-detail-{entry.index}" class="border-t border-slate-100 p-3" transition:slide>
			{#if entry.alternatives.length}
				<h3 class="text-sm font-semibold">Cards that scored higher</h3>
				<ul class="mt-1 text-sm">
					{#each entry.alternatives as alt (alt.score.oracle_id)}
						<li class="flex justify-between gap-3 py-0.5">
							<span class="truncate">{alt.info?.name ?? 'Unknown card'}</span>
							<span class="shrink-0 text-slate-600 tabular-nums">
								{formatWinRate(alt.score.gih_wr)} GIH WR
							</span>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-sm text-slate-600">Nothing in this pack scored higher than your pick.</p>
			{/if}

			<h3 class="mt-4 text-sm font-semibold">The pack ({pick.cards.length} different cards)</h3>
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
									? 'ring-4 ring-slate-900 ring-offset-1'
									: ''}"
							/>
						{:else}
							<div
								class="flex aspect-[488/680] items-center justify-center rounded-lg bg-slate-200 p-1 text-center"
							>
								{info?.name ?? 'Unknown card'}
							</div>
						{/if}
						<p class="mt-1 flex items-center justify-between gap-1">
							<span class="tabular-nums">{formatWinRate(card.gih_wr)}</span>
							{#if card.fitness_class}
								<span class="rounded px-1 text-[11px] {VERDICT_STYLE[card.fitness_class].chip}"
									>{VERDICT_STYLE[card.fitness_class].label}</span
								>
							{/if}
						</p>
						{#if taken}<p class="font-semibold">Your pick</p>{/if}
						{#if card.insufficient_data}<p class="text-slate-500">few games</p>{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</li>
