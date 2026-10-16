<script lang="ts">
	import type { Verdict } from '$lib/api/types';
	import { VERDICT_STYLE } from './model';

	let { verdict }: { verdict: Verdict } = $props();
	const style = $derived(VERDICT_STYLE[verdict]);
</script>

<!-- The label is always written out: colour alone would fail colour-blind readers. -->
<span
	class="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset {style.chip}"
	data-verdict={verdict}>{style.label}</span
>
