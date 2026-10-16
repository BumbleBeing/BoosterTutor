<script lang="ts">
	// One card in the deck builder's grid: placed at its column and row, and
	// the thing you drag, double-click, focus or right-click. It handles none of
	// that itself; the builder's drag controller and callbacks do.
	import CardFace from './CardFace.svelte';
	import type { DragController } from './drag.svelte';
	import { columnLeft, type Metrics } from './grid';
	import { HEADERS, SIDEBOARD, type Face } from './model';
	import { clearZoom, toggleZoom } from './zoom.svelte';

	let {
		key,
		face,
		col,
		row,
		m,
		drag,
		onactivate,
		onkeydown
	}: {
		key: string;
		face: Face;
		col: number;
		row: number; // its position in the column, 0 at the top
		m: Metrics;
		drag: DragController;
		onactivate: () => void; // a double-click
		onkeydown: (event: KeyboardEvent) => void;
	} = $props();

	// While it's being dragged, its place in the grid shows faded.
	const faded = $derived(drag.activeKey === key);
</script>

<div
	class="absolute cursor-grab overflow-hidden rounded-[4.5%/3.2%] shadow-sm ring-focus select-none hover:ring-2 focus-visible:ring-2 focus-visible:outline-none [@media(pointer:fine)]:touch-none {faded
		? 'opacity-30'
		: ''}"
	style="left:{columnLeft(m, col)}px; top:{row *
		m.strip}px; width:{m.colW}px; height:{m.cardH}px; z-index:{row + 1}"
	role="button"
	tabindex="0"
	data-key={key}
	data-col={col}
	aria-label="{face.name}, {col === SIDEBOARD ? 'sideboard' : `deck, mana value ${HEADERS[col]}`}"
	title={face.basic
		? 'Double-click to remove'
		: `Double-click to move it to the ${col === SIDEBOARD ? 'deck' : 'sideboard'}`}
	onpointerdown={(e) => drag.down(e, key, col)}
	onpointermove={drag.move}
	onpointerup={drag.up}
	onpointercancel={drag.cancel}
	ondblclick={onactivate}
	{onkeydown}
	oncontextmenu={(e) => toggleZoom(e, key, face.image, face.name)}
	onpointerleave={() => clearZoom(key)}
>
	<CardFace {face} />
</div>
