<script lang="ts">
	// Draws the zoomed card (see zoom.svelte.ts): 2.5x the card's size, centred
	// on it, then nudged to stay inside the window.
	import { zoom } from './zoom.svelte';

	let vw = $state(0);
	let vh = $state(0);
	const MARGIN = 8;

	const box = $derived.by(() => {
		if (!zoom.rect) return null;
		const r = zoom.rect;
		// 2.5x, unless that would not fit the window at all.
		const scale = Math.min(2.5, (vw - 2 * MARGIN) / r.width, (vh - 2 * MARGIN) / r.height);
		const w = r.width * scale;
		const h = r.height * scale;
		const clamp = (v: number, max: number) => Math.min(Math.max(v, MARGIN), max - MARGIN);
		return {
			left: clamp(r.left + r.width / 2 - w / 2, vw - w),
			top: clamp(r.top + r.height / 2 - h / 2, vh - h),
			w,
			h
		};
	});
</script>

<svelte:window
	bind:innerWidth={vw}
	bind:innerHeight={vh}
	onscroll={() => (zoom.key = zoom.src = zoom.rect = null)}
/>

{#if box}
	<div
		class="pointer-events-none fixed z-50 overflow-hidden rounded-[4.5%/3.2%] shadow-2xl"
		style="left:{box.left}px; top:{box.top}px; width:{box.w}px; height:{box.h}px"
	>
		{#if zoom.src}
			<img src={zoom.src} alt={zoom.name} class="h-full w-full" />
		{:else}
			<div class="flex h-full w-full items-center justify-center bg-white p-4 text-center text-2xl">
				{zoom.name}
			</div>
		{/if}
	</div>
{/if}
