<script lang="ts">
	// The deck builder (ADR 0025 s1), laid out like the practice draft's pool
	// grid: nine columns (mana value 0 to 6, 7+, then the sideboard) of card
	// images that overlap so only each card's title bar shows, except the last.
	//
	// It knows nothing about where its pool came from: an imported draft
	// today, a practice draft in Phase 7. It hands the finished 40 cards to
	// `onSubmit` and does nothing else.
	//
	// Drag a card to move it (drag.svelte.ts; where it lands is `dropTarget` in
	// grid.ts). Double-click a deck card to send it to the sideboard, or a
	// sideboard card back to its mana-value column; double-click a basic land
	// to remove it. Enter does the same from the keyboard, the arrow keys move
	// between cards (keyboard.ts), and right-click zooms a card to 2.5x.
	//
	// This file wires those pieces together and draws the grid.
	import { tick } from 'svelte';
	import BasicLandButtons from './BasicLandButtons.svelte';
	import CardFace from './CardFace.svelte';
	import ColumnHeaders from './ColumnHeaders.svelte';
	import DeckStatus from './DeckStatus.svelte';
	import GridCard from './GridCard.svelte';
	import ZoomLayer from './ZoomLayer.svelte';
	import { DragController } from './drag.svelte';
	import { GAP, columnLeft, dropTarget, gridHeight, metrics, type DropTarget } from './grid';
	import { arrowTarget, focusAfterActivate } from './keyboard';
	import { clearZoom } from './zoom.svelte';
	import {
		SIDEBOARD,
		deckSize,
		faceMap,
		flip,
		initialLayout,
		moveTo,
		toSubmission,
		without,
		type BasicLand,
		type PoolCard
	} from './model';

	let {
		pool,
		basicImages = {},
		onSubmit,
		submitting = false,
		submitLabel = 'Submit deck',
		confirmMessage = 'Only your first deck gets a written review. Later decks get ratings only.'
	}: {
		pool: PoolCard[];
		// Card art for each basic land by colour letter; a colour without one is drawn.
		basicImages?: Record<string, string | null>;
		onSubmit: (deck: ReturnType<typeof toSubmission>) => void | Promise<void>;
		submitting?: boolean;
		submitLabel?: string;
		confirmMessage?: string;
	} = $props();

	// The pool never changes while the builder is open, so the layout starts
	// from it once. Basics are added later; each is an entry of its own.
	// svelte-ignore state_referenced_locally
	let layout = $state(initialLayout(pool));
	let basics = $state<BasicLand[]>([]);
	let nextBasic = 0;
	let announcement = $state(''); // read out by screen readers

	let width = $state(0); // the scrolling panel, padding included
	let gridEl = $state<HTMLDivElement | null>(null);
	const m = $derived(metrics(width));
	const faces = $derived(faceMap(pool, basics, basicImages));

	function addBasic(colour: string, name: string) {
		const key = `b${nextBasic++}`;
		basics = [...basics, { key, colour }];
		layout = moveTo(layout, key, 0, layout[0].length);
		announcement = `Added a ${name}. ${deckSize(layout)} cards in the deck.`;
	}

	/** Double-click or Enter: a basic is removed, any other card changes side. */
	function activate(key: string) {
		const face = faces.get(key)!;
		clearZoom();
		if (face.basic) {
			layout = without(layout, key);
			basics = basics.filter((b) => b.key !== key);
			announcement = `Removed a ${face.name}.`;
		} else {
			const next = flip(layout, key, face.cmc);
			if (next === layout) return;
			layout = next;
			announcement = `${face.name} moved to the ${layout[SIDEBOARD].includes(key) ? 'sideboard' : 'deck'}.`;
		}
	}

	const drag = new DragController({
		// The pointer is in window coordinates; dropTarget wants the grid's.
		locate(x, y, key, fromCol) {
			if (!gridEl) return null;
			const rect = gridEl.getBoundingClientRect();
			const dragged = { key, fromCol, basic: !!faces.get(key)?.basic };
			return dropTarget(m, layout, dragged, x - rect.left, y - rect.top);
		},
		onStart: () => clearZoom(), // dragging always shrinks a zoomed card
		onDrop(key: string, { col, index }: DropTarget) {
			const next = moveTo(layout, key, col, index);
			if (JSON.stringify(next) !== JSON.stringify(layout)) layout = next;
		}
	});

	const focusCard = (key: string | null) =>
		key && gridEl?.querySelector<HTMLElement>(`[data-key="${key}"]`)?.focus();

	async function onkeydown(event: KeyboardEvent, key: string, col: number, i: number) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			// After the move the card is gone from here, so focus follows the card
			// (or, for a removed basic, its neighbour) rather than falling to the page.
			const removed = !!faces.get(key)?.basic;
			activate(key);
			await tick();
			focusCard(focusAfterActivate(layout, key, col, i, removed));
		} else if (event.key.startsWith('Arrow')) {
			event.preventDefault();
			focusCard(arrowTarget(layout, col, i, event.key));
		}
	}
</script>

<section aria-labelledby="deck-builder-help" class="text-ink">
	<p id="deck-builder-help" class="text-sm text-muted">
		Drag cards between columns, or double-click one to move it between your deck and sideboard
		(focus it and press Enter works too). Double-click a basic land to remove it. Right-click a card
		to enlarge it.
	</p>
	<p class="sr-only" aria-live="polite">{announcement}</p>

	<div class="mt-4 flex items-start gap-2 sm:gap-4">
		<BasicLandButtons onadd={addBasic} />

		<div class="min-w-0 flex-1">
			<DeckStatus
				size={deckSize(layout)}
				sideboard={layout[SIDEBOARD].length}
				{submitting}
				{submitLabel}
				{confirmMessage}
				onSubmit={() => onSubmit(toSubmission(layout, pool, basics))}
			/>

			<!-- On a narrow screen the grid scrolls sideways inside its panel, not the page. -->
			<div
				class="mt-3 overflow-x-auto rounded-2xl border border-line bg-surface p-3 shadow-sm"
				bind:clientWidth={width}
				data-pool-grid
			>
				<ColumnHeaders {layout} width={m.inner} />

				<div
					bind:this={gridEl}
					class="relative"
					style="height:{gridHeight(m, layout)}px; width:{m.inner}px"
				>
					<div
						class="absolute top-0 bottom-0 border-l border-dashed border-line-strong"
						style="left:{columnLeft(m, SIDEBOARD) - GAP / 2}px"
					></div>
					{#each layout as column, col (col)}
						{#each column as key, i (key)}
							<GridCard
								{key}
								face={faces.get(key)!}
								{col}
								row={i}
								{m}
								{drag}
								onactivate={() => activate(key)}
								onkeydown={(e) => onkeydown(e, key, col, i)}
							/>
						{/each}
					{/each}

					{#if drag.activeKey && drag.target}
						<!-- Where the card will go. -->
						<div
							class="pointer-events-none absolute z-[60] h-1 rounded-full {drag.target.allowed
								? 'bg-accent'
								: 'bg-danger-strong'}"
							style="left:{columnLeft(m, drag.target.col)}px; width:{m.colW}px; top:{Math.max(
								0,
								drag.target.index * m.strip - 3
							)}px"
						></div>
					{/if}
				</div>
			</div>
		</div>
	</div>
</section>

{#if drag.dragging?.active}
	{@const d = drag.dragging}
	<!-- The card under the pointer while dragging. -->
	<div
		class="pointer-events-none fixed z-[70] overflow-hidden rounded-[4.5%/3.2%] shadow-2xl"
		style="left:{d.x - d.grabX}px; top:{d.y - d.grabY}px; width:{m.colW}px; height:{m.cardH}px"
	>
		<CardFace face={faces.get(d.key)!} />
	</div>
{/if}

<ZoomLayer />
