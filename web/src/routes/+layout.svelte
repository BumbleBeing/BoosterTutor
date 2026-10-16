<script lang="ts">
	import './layout.css';
	import { resolve } from '$app/paths';
	import favicon from '$lib/assets/favicon.svg';
	import SeventeenLandsCredit from '$lib/review/SeventeenLandsCredit.svelte';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<!-- The shell every page sits in. The column stretches to the window's height
     so the footer stays at the bottom even on a short page. -->
<div class="flex min-h-screen flex-col">
	<header class="border-b border-line bg-surface">
		<div class="mx-auto flex max-w-6xl items-baseline gap-3 px-4 py-3">
			<a
				href={resolve('/')}
				class="font-display text-2xl font-semibold tracking-wide text-accent hover:text-accent-hover"
				>BoosterTutor</a
			>
			<span class="hidden text-sm text-muted sm:inline">a coach for Magic drafts</span>
		</div>
	</header>

	<div class="flex-1">{@render children()}</div>

	<!-- ADR 0002 s4 and ADR 0031 s7: the 17Lands credit on every review, so it lives here. -->
	<footer class="border-t border-line">
		<div class="mx-auto max-w-6xl px-4 py-5"><SeventeenLandsCredit /></div>
	</footer>
</div>
