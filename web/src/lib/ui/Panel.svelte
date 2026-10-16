<script lang="ts">
	// A sheet of lighter paper on the parchment page: the box around a summary,
	// a pick, the Deck Ratings. `as` picks the element (section, li, aside...)
	// so the page keeps its meaning for screen readers; `padded={false}` leaves
	// the inside to the caller, for rows that hold their own buttons.
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		as = 'div',
		padded = true,
		children,
		class: extra = '',
		...rest
	}: {
		as?: 'div' | 'section' | 'li' | 'aside' | 'article';
		padded?: boolean;
		children: Snippet;
		class?: string;
	} & HTMLAttributes<HTMLElement> = $props();
</script>

<svelte:element
	this={as}
	class="rounded-lg border border-line bg-surface shadow-sm {padded ? 'p-5' : ''} {extra}"
	{...rest}
>
	{@render children()}
</svelte:element>
