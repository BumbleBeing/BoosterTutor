<script lang="ts">
	// What a card in the deck builder looks like: its image when there is one,
	// a drawn card in the land's colours for a basic land the set has no art
	// for, or otherwise a plain box with its name. It fills whatever box it is
	// put in: a card in the grid, the card under the pointer while dragging.
	import { TONE_CLASSES, manaTone } from '$lib/ui/tones';
	import type { Face } from './model';

	let { face }: { face: Face } = $props();
</script>

{#if face.image}
	<!-- draggable=false: the browser's own image drag would fight ours. -->
	<img src={face.image} alt="" draggable="false" class="h-full w-full" />
{:else if face.basic}
	<div
		class="flex h-full w-full flex-col items-center p-1 text-center text-[11px] font-medium ring-1 ring-inset {TONE_CLASSES[
			manaTone(face.basic)
		]}"
	>
		{face.name}
		<span class="mt-auto mb-auto text-3xl font-bold opacity-60">{face.basic}</span>
	</div>
{:else}
	<div
		class="flex h-full w-full items-start justify-center bg-sunken p-1 text-center text-[11px] ring-1 ring-line"
	>
		{face.name}
	</div>
{/if}
