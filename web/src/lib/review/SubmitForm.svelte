<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ApiError, importDraft } from '$lib/api/client';
	import ErrorState from './ErrorState.svelte';

	let link = $state('');
	let busy = $state(false);
	let error = $state<ApiError | null>(null);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!link.trim()) {
			error = new ApiError('invalid_input', 'empty');
			return;
		}
		busy = true;
		error = null;
		try {
			const { draft_id } = await importDraft(link.trim());
			await goto(resolve('/draft/[id]', { id: draft_id }));
		} catch (err) {
			error = err instanceof ApiError ? err : new ApiError('unknown', String(err));
		} finally {
			busy = false;
		}
	}
</script>

<form onsubmit={submit} class="space-y-3">
	<label for="draft-link" class="block text-sm font-medium">17Lands draft link or ID</label>
	<div class="flex flex-col gap-2 sm:flex-row">
		<input
			id="draft-link"
			type="text"
			bind:value={link}
			placeholder="https://www.17lands.com/data/draft?draft_id=…"
			autocomplete="off"
			spellcheck="false"
			class="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-base focus:border-slate-900 focus:outline-none"
		/>
		<button
			type="submit"
			disabled={busy}
			class="rounded-md bg-slate-900 px-5 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-60"
		>
			{busy ? 'Fetching…' : 'Review my draft'}
		</button>
	</div>
	{#if error}
		<ErrorState {error} homeLink={false} />
	{/if}
</form>
