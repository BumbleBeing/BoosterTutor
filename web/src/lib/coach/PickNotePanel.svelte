<script lang="ts">
	// What a Noted Pick's speech bubble opens. Without a coach (the public
	// page) it is the sign-in prompt. With one (the admin page) opening it asks
	// for the note: the stored one, or a new one Claude writes (ADR 0031 s2).
	import { onMount } from 'svelte';
	import type { PickAnalysis } from '$lib/api/types';
	import { describeError } from '$lib/review/model';
	import Button from '$lib/ui/Button.svelte';
	import Chip from '$lib/ui/Chip.svelte';
	import { useCoach } from './coach.svelte';

	let { pick, id }: { pick: PickAnalysis; id: string } = $props();

	const coach = useCoach();
	const noteState = $derived(coach?.noteFor(pick));

	// The panel exists only while open, so mounting it is "the pick was opened".
	onMount(() => {
		coach?.writeNote(pick);
	});
</script>

<div
	{id}
	class="mx-3 mb-3 rounded-md border border-periwinkle-line bg-periwinkle p-3 text-sm text-periwinkle-ink"
	aria-live="polite"
>
	{#if !coach || !noteState}
		Sign in for a coach's note on this pick.
	{:else if noteState.status === 'written'}
		<p>{noteState.note.note}</p>
		{#if noteState.note.stale}
			<Chip tone="questionable" size="xs" class="mt-2">Written against older stats</Chip>
		{/if}
	{:else if noteState.status === 'failed'}
		{@const copy = describeError(noteState.error)}
		<p class="font-medium">{copy.title}</p>
		<p class="mt-1">{copy.body}</p>
		{#if copy.retryable}
			<Button variant="secondary" size="sm" class="mt-2" onclick={() => coach?.writeNote(pick)}
				>Try again</Button
			>
		{/if}
	{:else}
		<!-- 'writing', or 'idle' for the moment before onMount asks. -->
		<p class="animate-pulse">The coach is writing a note on this pick…</p>
	{/if}
</div>
