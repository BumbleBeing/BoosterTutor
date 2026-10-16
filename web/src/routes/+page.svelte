<script lang="ts">
	import SubmitForm from '$lib/review/SubmitForm.svelte';
</script>

<svelte:head><title>BoosterTutor — review your Magic draft</title></svelte:head>

<main class="mx-auto max-w-2xl px-4 py-12 sm:py-20">
	<h1 class="text-4xl font-semibold sm:text-5xl">Review your draft</h1>
	<p class="mt-3 text-lg text-muted">
		Paste a 17Lands draft link and see every pick graded: what you took, what you passed, and which
		picks are worth a second look.
	</p>
	<div class="mt-8">
		<SubmitForm />
	</div>
	<p class="mt-4 text-sm text-muted">
		On 17Lands, open your draft and copy its link. The draft must be shared publicly.
	</p>
</main>
