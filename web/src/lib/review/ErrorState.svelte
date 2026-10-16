<script lang="ts">
	import { resolve } from '$app/paths';
	import type { ApiError } from '$lib/api/client';
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
<div role="alert" class="rounded-lg border border-red-200 bg-red-50 p-5 text-red-950">
	<h2 class="text-lg font-semibold">{copy.title}</h2>
	<p class="mt-2 text-sm">{copy.body}</p>
	<div class="mt-4 flex flex-wrap gap-3 text-sm">
		{#if copy.retryable && onretry}
			<button
				type="button"
				class="rounded-md bg-red-900 px-3 py-1.5 font-medium text-white hover:bg-red-800"
				onclick={onretry}>Try again</button
			>
		{/if}
		{#if homeLink}
			<a class="px-1 py-1.5 font-medium underline" href={resolve('/')}>Submit a different draft</a>
		{/if}
	</div>
</div>
