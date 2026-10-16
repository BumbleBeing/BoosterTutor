<script lang="ts">
	// The row of headings over the deck builder's grid ("0" to "7+", then
	// "Sideboard"), each with how many cards its column holds. The sideboard's
	// heading is darker, to set it apart.
	import { COLUMNS, HEADERS, SIDEBOARD, type Layout } from './model';

	let { layout, width }: { layout: Layout; width: number } = $props();
</script>

<div
	class="mb-2 grid gap-2"
	style="grid-template-columns: repeat({COLUMNS}, minmax(0, 1fr)); width:{width}px"
>
	{#each HEADERS as header, col (col)}
		<div
			class="flex justify-between border-b pb-0.5 text-[11px] font-semibold tracking-wider uppercase {col ===
			SIDEBOARD
				? 'border-line-strong text-ink'
				: 'border-line text-muted'}"
		>
			<span>{header}</span><span class="font-normal text-muted tabular-nums"
				>{layout[col].length || ''}</span
			>
		</div>
	{/each}
</div>
