<script lang="ts">
	// Puts a coach in context for everything inside it. Svelte reads context
	// only while a component starts, so the admin page wraps the review in
	// this and re-creates it (with {#key}) when the coach changes.
	import type { Snippet } from 'svelte';
	import { type Coach, provideCoach } from './coach.svelte';

	let { coach, children }: { coach: Coach | null; children: Snippet } = $props();

	// Read once, on purpose: the {#key} around this component makes a new one
	// whenever the coach changes.
	// svelte-ignore state_referenced_locally
	if (coach) provideCoach(coach);
</script>

{@render children()}
