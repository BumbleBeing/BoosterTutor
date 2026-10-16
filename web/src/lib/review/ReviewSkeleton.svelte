<!-- A plain placeholder while the review loads. No fake progress: the call is one quick request. -->
<div aria-busy="true" aria-label="Loading your draft review" role="status" class="animate-pulse">
	<div class="h-24 rounded-lg bg-slate-200"></div>
	<div class="mt-8 space-y-3">
		{#each [0, 1, 2, 3, 4, 5, 6, 7] as i (i)}
			<div class="h-14 rounded-lg bg-slate-100"></div>
		{/each}
	</div>
</div>
