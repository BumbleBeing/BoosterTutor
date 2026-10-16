<script lang="ts">
	// One "+ Plains" button per basic land, in the land's own colours (the mana
	// tokens from layout.css). Each press adds one land to the deck.
	import { TONE_CLASSES, manaTone } from '$lib/ui/tones';
	import { BASIC_LANDS } from './model';

	let { onadd }: { onadd: (colour: string, name: string) => void } = $props();
</script>

<div class="flex shrink-0 flex-col gap-2" role="group" aria-label="Add basic lands">
	{#each BASIC_LANDS as { colour, name } (colour)}
		<button
			type="button"
			data-add-basic={colour}
			class="touch-manipulation rounded px-2 py-2 text-left text-sm font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus {TONE_CLASSES[
				manaTone(colour)
			]}"
			onclick={() => onadd(colour, name)}
		>
			+ {name}
		</button>
	{/each}
</div>
