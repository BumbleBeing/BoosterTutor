<script lang="ts">
	// A small coloured label: a verdict, a grade, a colour of Magic.
	// `shape="pill"` is a rounded label ("Solid"); `shape="square"` is a fixed
	// box for a single letter ("A"), in three sizes.
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { TONE_CLASSES, type Tone } from './tones';

	let {
		tone,
		shape = 'pill',
		size = 'sm',
		children,
		class: extra = '',
		...rest
	}: {
		tone: Tone;
		shape?: 'pill' | 'square';
		size?: 'xs' | 'sm' | 'lg';
		children: Snippet;
		class?: string;
	} & HTMLAttributes<HTMLSpanElement> = $props();

	const SHAPES = {
		pill: {
			xs: 'rounded px-1 text-[11px]',
			sm: 'rounded-full px-2.5 py-0.5 text-xs',
			lg: 'rounded-full px-3 py-1 text-sm'
		},
		square: {
			xs: 'h-5 w-5 rounded text-xs',
			sm: 'h-7 w-7 rounded',
			lg: 'h-14 w-14 rounded-lg text-3xl'
		}
	};
</script>

<!-- Pair a tone with words: colour alone would fail colour-blind readers. -->
<span
	class="inline-flex shrink-0 items-center justify-center whitespace-nowrap ring-1 ring-inset {shape ===
	'square'
		? 'font-bold'
		: 'font-medium'} {SHAPES[shape][size]} {TONE_CLASSES[tone]} {extra}"
	{...rest}>{@render children()}</span
>
