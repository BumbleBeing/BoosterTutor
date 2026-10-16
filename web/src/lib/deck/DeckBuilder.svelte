<script lang="ts">
	// The deck builder (ADR 0025 s1). It knows nothing about where its pool
	// came from: an imported draft today, a practice draft in Phase 7. It
	// hands the finished 40 cards to `onSubmit` and does nothing else.
	import { tick } from 'svelte';
	import {
		BASIC_LANDS,
		DECK_SIZE,
		LAND_COLUMN,
		basicsTotal,
		deckSize,
		emptyBasics,
		inColumns,
		toSubmission,
		type PoolCard
	} from './model';

	let {
		pool,
		onSubmit,
		submitting = false,
		submitLabel = 'Submit deck',
		confirmMessage = 'Only your first deck gets a written review. Later decks get ratings only.'
	}: {
		pool: PoolCard[];
		onSubmit: (deck: ReturnType<typeof toSubmission>) => void | Promise<void>;
		submitting?: boolean;
		submitLabel?: string;
		confirmMessage?: string;
	} = $props();

	// Which pool cards are in the deck (by `key`); the rest are the sideboard.
	let deckKeys = $state<string[]>([]);
	let basics = $state(emptyBasics());
	let confirming = $state(false);
	let announcement = $state('');
	let root: HTMLElement | undefined;

	const main = $derived(pool.filter((c) => deckKeys.includes(c.key)));
	const side = $derived(pool.filter((c) => !deckKeys.includes(c.key)));
	const size = $derived(deckSize(main.length, basics));
	const deckColumns = $derived(inColumns(main));
	const sideColumns = $derived(inColumns(side));
	// Closing the confirmation as soon as the deck stops being 40 cards.
	const ready = $derived(size === DECK_SIZE);

	// A colour stripe on each card; the name and cost carry the information.
	const STRIPE: Record<string, string> = {
		W: 'border-l-amber-300',
		U: 'border-l-sky-500',
		B: 'border-l-slate-700',
		R: 'border-l-red-500',
		G: 'border-l-green-600'
	};
	function stripe(colors: string): string {
		if (colors.length === 0) return 'border-l-slate-300';
		return colors.length > 1 ? 'border-l-yellow-500' : (STRIPE[colors] ?? 'border-l-slate-300');
	}

	const cost = (c: PoolCard) => (c.manaCost ?? '').replace(/[{}]/g, '');

	/**
	 * After a keyboard move the card under the cursor is gone, so focus would
	 * fall back to the page. Hand it to the card's neighbour in the same column.
	 */
	async function refocusNeighbour(button: HTMLElement | null) {
		const next = button?.nextElementSibling ?? button?.previousElementSibling ?? null;
		const target = next instanceof HTMLElement ? next : (button?.closest('[data-column]') ?? null);
		await tick();
		if (target instanceof HTMLElement && root?.contains(target)) target.focus();
	}

	function move(card: PoolCard, button: HTMLElement | null, byKeyboard: boolean) {
		const toSide = deckKeys.includes(card.key);
		deckKeys = toSide ? deckKeys.filter((k) => k !== card.key) : [...deckKeys, card.key];
		announcement = `${card.name} moved to the ${toSide ? 'sideboard' : 'deck'}.`;
		if (byKeyboard) refocusNeighbour(button);
	}

	function addBasic(colour: string, name: string) {
		basics[colour] += 1;
		announcement = `Added a ${name}. ${basicsTotal(basics)} basic lands.`;
	}

	function removeBasic(
		colour: string,
		name: string,
		button: HTMLElement | null,
		byKeyboard: boolean
	) {
		basics[colour] -= 1;
		announcement = `Removed a ${name}.`;
		if (byKeyboard && basics[colour] === 0) refocusNeighbour(button);
	}

	// A mouse click has `detail` 1 or more, a double-click 2; a click made with
	// the keyboard (Enter or Space on a focused button) has 0. So a mouse needs
	// the double-click, while a keyboard user needs only one keypress.
	const byKeyboard = (e: MouseEvent) => e.detail === 0;

	async function submit() {
		confirming = false;
		await onSubmit(toSubmission(main, basics));
	}
</script>

{#snippet cardColumns(columns: ReturnType<typeof inColumns>, inDeck: boolean)}
	<div class="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3">
		{#each columns as { column, cards } (column)}
			<div data-column={column} tabindex="-1" class="min-w-0">
				<h4 class="mb-1 border-b border-slate-300 text-xs font-semibold text-slate-500">
					{column === LAND_COLUMN ? 'Lands' : `Mana value ${column}`}
					<span class="font-normal"
						>({cards.length + (inDeck && column === LAND_COLUMN ? basicsTotal(basics) : 0)})</span
					>
				</h4>
				<div class="flex flex-col gap-1">
					{#each cards as card (card.key)}
						<button
							type="button"
							data-card
							title="{card.typeLine}. Double-click, or press Enter, to move it to the {inDeck
								? 'sideboard'
								: 'deck'}."
							class="touch-manipulation rounded border border-l-4 border-slate-200 bg-white px-2 py-1 text-left text-sm select-none hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-indigo-600 {stripe(
								card.colors
							)}"
							ondblclick={(e) => move(card, e.currentTarget, false)}
							onclick={(e) => byKeyboard(e) && move(card, e.currentTarget, true)}
						>
							<span class="block leading-tight break-words">{card.name}</span>
							{#if cost(card)}<span class="block text-xs text-slate-500">{cost(card)}</span>{/if}
						</button>
					{/each}
					{#if inDeck && column === LAND_COLUMN}
						{#each BASIC_LANDS as { colour, name } (colour)}
							{#if basics[colour] > 0}
								<button
									type="button"
									data-basic={colour}
									title="Double-click, or press Enter, to remove one {name}."
									class="touch-manipulation rounded border border-l-4 border-slate-200 bg-slate-50 px-2 py-1 text-left text-sm select-none hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-indigo-600 {stripe(
										colour
									)}"
									ondblclick={(e) => removeBasic(colour, name, e.currentTarget, false)}
									onclick={(e) => byKeyboard(e) && removeBasic(colour, name, e.currentTarget, true)}
								>
									{name} <span class="tabular-nums">× {basics[colour]}</span>
								</button>
							{/if}
						{/each}
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/snippet}

<section bind:this={root} aria-labelledby="deck-builder-help" class="text-slate-900">
	<p id="deck-builder-help" class="text-sm text-slate-600">
		Double-click a card to move it between your deck and sideboard, or focus it and press Enter.
		Double-click a basic land to remove one.
	</p>
	<p class="sr-only" aria-live="polite">{announcement}</p>

	<div class="mt-4 flex gap-3 sm:gap-5">
		<div class="flex shrink-0 flex-col gap-2" role="group" aria-label="Add basic lands">
			{#each BASIC_LANDS as { colour, name } (colour)}
				<button
					type="button"
					data-add-basic={colour}
					class="touch-manipulation rounded border border-l-4 border-slate-300 bg-white px-2 py-2 text-left text-sm font-medium hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-indigo-600 {stripe(
						colour
					)}"
					onclick={() => addBasic(colour, name)}
				>
					+ {name}
				</button>
			{/each}
		</div>

		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
				<h3 class="text-lg font-semibold">Deck</h3>
				<p
					class="text-lg font-semibold tabular-nums {ready ? 'text-emerald-800' : ''}"
					data-deck-count
				>
					{size} / {DECK_SIZE}
					<span class="sr-only">cards</span>
				</p>
				<button
					type="button"
					class="ml-auto rounded bg-indigo-700 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
					disabled={!ready || submitting}
					onclick={() => (confirming = true)}
				>
					{submitting ? 'Rating…' : submitLabel}
				</button>
			</div>
			{#if !ready}
				<p class="mt-1 text-sm text-slate-500">
					{size < DECK_SIZE ? `${DECK_SIZE - size} more to go.` : `${size - DECK_SIZE} too many.`}
					A deck must be exactly {DECK_SIZE} cards.
				</p>
			{/if}

			{#if confirming && ready}
				<div
					role="group"
					aria-label="Confirm submission"
					class="mt-3 rounded border border-indigo-200 bg-indigo-50 p-3 text-sm"
				>
					<p>{confirmMessage}</p>
					<div class="mt-2 flex gap-2">
						<button
							type="button"
							class="rounded bg-indigo-700 px-3 py-1.5 font-medium text-white hover:bg-indigo-800"
							onclick={submit}>Yes, submit</button
						>
						<button
							type="button"
							class="rounded border border-slate-300 bg-white px-3 py-1.5 hover:bg-slate-50"
							onclick={() => (confirming = false)}>Cancel</button
						>
					</div>
				</div>
			{/if}

			<div class="mt-3">{@render cardColumns(deckColumns, true)}</div>

			<h3 class="mt-8 text-lg font-semibold">
				Sideboard <span class="text-base font-normal text-slate-500">({side.length})</span>
			</h3>
			<div class="mt-3">{@render cardColumns(sideColumns, false)}</div>
		</div>
	</div>
</section>
