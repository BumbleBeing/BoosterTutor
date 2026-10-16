<script lang="ts">
	// The app's button. `primary` is the one main action in a place (lapis
	// blue), `secondary` is everything else (outlined), and `danger` retries a
	// failure inside an error panel. Any other attribute (type, disabled,
	// onclick, aria-*) passes straight through to the <button>.
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	let {
		variant = 'primary',
		size = 'md',
		type = 'button',
		children,
		class: extra = '',
		...rest
	}: {
		variant?: 'primary' | 'secondary' | 'danger';
		size?: 'sm' | 'md';
		children: Snippet;
		class?: string;
	} & HTMLButtonAttributes = $props();

	const VARIANTS = {
		primary: 'bg-accent text-accent-ink hover:bg-accent-hover',
		secondary: 'border border-line-strong bg-surface text-ink hover:bg-page',
		danger: 'bg-danger-strong text-accent-ink hover:bg-danger-ink'
	};
	const SIZES = { sm: 'px-3 py-1.5 text-sm', md: 'px-5 py-2' };
</script>

<!-- A disabled button greys out the same way whatever its variant. -->
<button
	{type}
	class="touch-manipulation rounded-md font-medium disabled:cursor-not-allowed disabled:border-transparent disabled:bg-sunken disabled:text-muted {VARIANTS[
		variant
	]} {SIZES[size]} {extra}"
	{...rest}>{@render children()}</button
>
