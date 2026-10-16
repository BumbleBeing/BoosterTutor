<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ApiError, importDraft } from '$lib/api/client';
	import Button from '$lib/ui/Button.svelte';
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
			class="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 py-2 text-base placeholder:text-muted focus:border-accent"
		/>
		<Button type="submit" disabled={busy}>
			{busy ? 'Fetching…' : 'Review my draft'}
		</Button>
	</div>
	{#if error}
		<ErrorState {error} homeLink={false} />
	{/if}
</form>
