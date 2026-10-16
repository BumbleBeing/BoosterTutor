<script lang="ts">
	// The bar above the deck builder's grid: the "37 / 40" count, how many cards
	// are in the sideboard, and the submit button. Submitting asks first: the
	// button opens a confirm box, and only "Yes, submit" calls `onSubmit`.
	import Button from '$lib/ui/Button.svelte';
	import { DECK_SIZE } from './model';

	let {
		size,
		sideboard,
		submitting,
		submitLabel,
		confirmMessage,
		onSubmit
	}: {
		size: number; // cards in the deck, basics included
		sideboard: number;
		submitting: boolean;
		submitLabel: string;
		confirmMessage: string;
		onSubmit: () => void | Promise<void>;
	} = $props();

	let confirming = $state(false);
	const ready = $derived(size === DECK_SIZE);

	async function submit() {
		confirming = false;
		await onSubmit();
	}
</script>

<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
	<h3 class="text-lg font-semibold">Deck</h3>
	<p class="text-lg font-semibold tabular-nums {ready ? 'text-success-ink' : ''}" data-deck-count>
		{size} / {DECK_SIZE}
		<span class="sr-only">cards</span>
	</p>
	<p class="text-sm text-muted">
		Sideboard <span class="tabular-nums">{sideboard}</span>
	</p>
	<Button
		size="sm"
		class="ml-auto"
		disabled={!ready || submitting}
		onclick={() => (confirming = true)}
	>
		{submitting ? 'Rating…' : submitLabel}
	</Button>
</div>
{#if !ready}
	<p class="mt-1 text-sm text-muted">
		{size < DECK_SIZE ? `${DECK_SIZE - size} more to go.` : `${size - DECK_SIZE} too many.`}
		A deck must be exactly {DECK_SIZE} cards.
	</p>
{/if}

<!-- The deck can change while this is open; it hides itself unless the deck is still 40. -->
{#if confirming && ready}
	<div
		role="group"
		aria-label="Confirm submission"
		class="mt-3 rounded border border-periwinkle-line bg-periwinkle p-3 text-sm text-periwinkle-ink"
	>
		<p>{confirmMessage}</p>
		<div class="mt-2 flex gap-2">
			<Button size="sm" onclick={submit}>Yes, submit</Button>
			<Button size="sm" variant="secondary" onclick={() => (confirming = false)}>Cancel</Button>
		</div>
	</div>
{/if}
