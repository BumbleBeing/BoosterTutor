<script lang="ts">
	import { resolve } from '$app/paths';
	import type { ApiError } from '$lib/api/client';
	import Button from '$lib/ui/Button.svelte';
	import { describeError } from './model';

	let {
		error,
		onretry,
		homeLink = true
	}: {
		error: Pick<ApiError, 'kind' | 'message' | 'retryAfter'>;
		onretry?: () => void;
		// The submit form is already on the home page, so it turns this off.
		homeLink?: boolean;
	} = $props();
	const copy = $derived(describeError(error));
</script>

<!-- role="alert" makes screen readers announce it when it appears. -->
<div role="alert" class="rounded-lg border border-danger-line bg-danger p-5 text-danger-ink">
	<h2 class="text-lg font-semibold">{copy.title}</h2>
	<p class="mt-2 text-sm">{copy.body}</p>
	<div class="mt-4 flex flex-wrap gap-3 text-sm">
		{#if copy.retryable && onretry}
			<Button variant="danger" size="sm" onclick={onretry}>Try again</Button>
		{/if}
		{#if homeLink}
			<a class="px-1 py-1.5 font-medium underline" href={resolve('/')}>Submit a different draft</a>
		{/if}
	</div>
</div>
