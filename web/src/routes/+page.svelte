<script lang="ts">
	import SubmitForm from '$lib/review/SubmitForm.svelte';
	import SeventeenLandsCredit from '$lib/review/SeventeenLandsCredit.svelte';
</script>

<svelte:head><title>BoosterTutor — review your Magic draft</title></svelte:head>

<main class="mx-auto max-w-2xl px-4 py-12 sm:py-20">
	<h1 class="text-3xl font-bold sm:text-4xl">BoosterTutor</h1>
	<p class="mt-3 text-lg text-slate-700">
		Paste a 17Lands draft link and see every pick graded: what you took, what you passed, and which
		picks are worth a second look.
	</p>
	<div class="mt-8">
		<SubmitForm />
	</div>
	<p class="mt-4 text-sm text-slate-500">
		On 17Lands, open your draft and copy its link. The draft must be shared publicly.
	</p>
	<div class="mt-12"><SeventeenLandsCredit /></div>
</main>
