<script lang="ts">
	// The deck builder (ADR 0025 s1), laid out like the practice draft's pool
	// grid: nine columns (mana value 0 to 6, 7+, then the sideboard) of card
	// images that overlap so only each card's title bar shows, except the last.
	//
	// It knows nothing about where its pool came from: an imported draft
	// today, a practice draft in Phase 7. It hands the finished 40 cards to
	// `onSubmit` and does nothing else.
	//
	// Dragging uses pointer events, so a finger works as well as a mouse:
	//   * drop onto the card at position n: the dragged card takes position n,
	//     and that card and everything below it move down one
	//   * drop below a column: the card goes directly under its last card
	//   * the column it left closes up, so nothing ever floats
	// Double-click a deck card to send it to the sideboard, or a sideboard
	// card back to its mana-value column. Double-click a basic land to remove
	// it. Enter does the same from the keyboard, the arrow keys move between
	// cards, and right-click zooms a card to 2.5x.
	import { tick } from 'svelte';
	import {
		BASIC_LANDS,
		COLUMNS,
		DECK_SIZE,
		HEADERS,
		MAX_CARDS,
		SIDEBOARD,
		deckSize,
		flip,
		initialLayout,
		moveTo,
		toSubmission,
		without,
		type BasicLand,
		type PoolCard
	} from './model';
	import Button from '$lib/ui/Button.svelte';
	import { TONE_CLASSES, manaTone } from '$lib/ui/tones';
	import { clearZoom, toggleZoom } from './zoom.svelte';
	import ZoomLayer from './ZoomLayer.svelte';

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
	let confirming = $state(false);
	let announcement = $state('');

	const GAP = 8; // px between columns
	const CARD_RATIO = 680 / 488; // height / width of a Scryfall card image
	const STRIP = 0.13; // the share of a card's height its title bar takes
	const MIN_COL = 56; // narrower than this and the grid scrolls sideways instead

	let width = $state(0); // the scrolling panel, padding included
	let gridEl = $state<HTMLDivElement | null>(null);

	const inner = $derived(Math.max(MIN_COL * COLUMNS + GAP * (COLUMNS - 1), width - 24)); // minus the p-3
	const colW = $derived((inner - GAP * (COLUMNS - 1)) / COLUMNS);
	const cardH = $derived(colW * CARD_RATIO);
	const strip = $derived(cardH * STRIP);
	const columnHeight = (n: number) => (n === 0 ? cardH : (n - 1) * strip + cardH);
	const gridHeight = $derived(Math.max(...layout.map((column) => columnHeight(column.length))));

	const size = $derived(deckSize(layout));
	const ready = $derived(size === DECK_SIZE);

	type Face = { name: string; cmc: number; image: string | null; basic: string | null };
	const faces = $derived(
		new Map<string, Face>([
			...pool.map((c): [string, Face] => [
				c.key,
				{ name: c.name, cmc: c.cmc, image: c.image, basic: null }
			]),
			...basics.map((b): [string, Face] => {
				const land = BASIC_LANDS.find((l) => l.colour === b.colour)!;
				return [
					b.key,
					{ name: land.name, cmc: 0, image: basicImages[b.colour] ?? null, basic: b.colour }
				];
			})
		])
	);

	// A basic land's colours (its add button, and a drawn face when the set has
	// no art for it): the mana tokens from layout.css.
	const basicFace = (colour: string) => TONE_CLASSES[manaTone(colour)];

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

	// --- dragging --------------------------------------------------------
	type Drag = {
		key: string;
		fromCol: number;
		pointerId: number;
		startX: number;
		startY: number;
		x: number;
		y: number;
		grabX: number; // where on the card it was grabbed, so it doesn't jump
		grabY: number;
		active: boolean; // false until the pointer has moved a few pixels
	};
	let drag = $state<Drag | null>(null);
	let target = $state<{ col: number; index: number; allowed: boolean } | null>(null);

	function onpointerdown(event: PointerEvent, key: string, fromCol: number) {
		if (event.button !== 0) return;
		const el = event.currentTarget as HTMLElement;
		try {
			el.setPointerCapture(event.pointerId); // keeps the drag going outside the card
		} catch {
			// No such active pointer (a synthetic event): the drag still works.
		}
		const rect = el.getBoundingClientRect();
		drag = {
			key,
			fromCol,
			pointerId: event.pointerId,
			startX: event.clientX,
			startY: event.clientY,
			x: event.clientX,
			y: event.clientY,
			grabX: event.clientX - rect.left,
			grabY: event.clientY - rect.top,
			active: false
		};
	}

	function onpointermove(event: PointerEvent) {
		if (!drag || event.pointerId !== drag.pointerId) return;
		drag.x = event.clientX;
		drag.y = event.clientY;
		if (!drag.active && Math.hypot(drag.x - drag.startX, drag.y - drag.startY) > 5) {
			drag.active = true;
			clearZoom(); // dragging always shrinks a zoomed card
		}
		if (drag.active) target = dropTarget(drag.x, drag.y);
	}

	/** Which column, and which position in it once the card has left its old place. */
	function dropTarget(x: number, y: number) {
		if (!gridEl || !drag) return null;
		const rect = gridEl.getBoundingClientRect();
		const col = Math.min(COLUMNS - 1, Math.max(0, Math.floor((x - rect.left) / (colW + GAP))));
		const column = layout[col];
		const lengthAfter = column.length - (col === drag.fromCol ? 1 : 0);
		const relY = y - rect.top;
		let index: number;
		if (column.length === 0 || relY > columnHeight(column.length)) {
			index = lengthAfter; // below the column: directly under its last card
		} else {
			// Onto the card at n: take position n.
			const n = Math.min(Math.max(0, Math.floor(relY / strip)), column.length - 1);
			index = Math.min(n, lengthAfter);
		}
		// A basic land can't go in the sideboard: it would just be a card nobody plays.
		const basicInSideboard = col === SIDEBOARD && faces.get(drag.key)?.basic;
		const allowed = !basicInSideboard && (col === drag.fromCol || column.length < MAX_CARDS);
		return { col, index, allowed };
	}

	function onpointerup(event: PointerEvent) {
		if (!drag || event.pointerId !== drag.pointerId) return;
		const done = drag;
		const where = done.active ? dropTarget(event.clientX, event.clientY) : null;
		drag = null;
		target = null;
		if (!where || !where.allowed) return;
		const next = moveTo(layout, done.key, where.col, where.index);
		if (JSON.stringify(next) !== JSON.stringify(layout)) layout = next;
	}

	function onpointercancel() {
		drag = null;
		target = null;
	}

	// --- keyboard --------------------------------------------------------
	/** Enter acts, the arrows move between cards (up/down in a column, left/right across). */
	async function onkeydown(event: KeyboardEvent, key: string, col: number, i: number) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			// After the move the card is gone from here, so focus follows the card
			// (or, for a removed basic, its neighbour) rather than falling to the page.
			const removed = !!faces.get(key)?.basic;
			activate(key);
			await tick();
			const keep = removed ? (layout[col][Math.min(i, layout[col].length - 1)] ?? null) : key;
			if (keep) gridEl?.querySelector<HTMLElement>(`[data-key="${keep}"]`)?.focus();
			return;
		}
		let c = col;
		let r = i;
		if (event.key === 'ArrowUp') r--;
		else if (event.key === 'ArrowDown') r++;
		else if (event.key === 'ArrowLeft') c--;
		else if (event.key === 'ArrowRight') c++;
		else return;
		event.preventDefault();
		// Skip empty columns when moving sideways.
		while (c >= 0 && c < COLUMNS && event.key.startsWith('ArrowL') && !layout[c].length) c--;
		while (c >= 0 && c < COLUMNS && event.key.startsWith('ArrowR') && !layout[c].length) c++;
		if (c < 0 || c >= COLUMNS || !layout[c].length) return;
		r = Math.min(Math.max(r, 0), layout[c].length - 1);
		gridEl?.querySelector<HTMLElement>(`[data-key="${layout[c][r]}"]`)?.focus();
	}

	async function submit() {
		confirming = false;
		await onSubmit(toSubmission(layout, pool, basics));
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
		<div class="flex shrink-0 flex-col gap-2" role="group" aria-label="Add basic lands">
			{#each BASIC_LANDS as { colour, name } (colour)}
				<button
					type="button"
					data-add-basic={colour}
					class="touch-manipulation rounded px-2 py-2 text-left text-sm font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus {basicFace(
						colour
					)}"
					onclick={() => addBasic(colour, name)}
				>
					+ {name}
				</button>
			{/each}
		</div>

		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
				<h3 class="text-lg font-semibold">Deck</h3>
				<p
					class="text-lg font-semibold tabular-nums {ready ? 'text-success-ink' : ''}"
					data-deck-count
				>
					{size} / {DECK_SIZE}
					<span class="sr-only">cards</span>
				</p>
				<p class="text-sm text-muted">
					Sideboard <span class="tabular-nums">{layout[SIDEBOARD].length}</span>
				</p>
				<Button
					size="sm"
					class="ml-auto"
					disabled={!ready || submitting}
					onclick={() => (confirming = true)}
				>
					{submitting ? 'Rating…' : submitLabel}
				</Button>
			</div>
			{#if !ready}
				<p class="mt-1 text-sm text-muted">
					{size < DECK_SIZE ? `${DECK_SIZE - size} more to go.` : `${size - DECK_SIZE} too many.`}
					A deck must be exactly {DECK_SIZE} cards.
				</p>
			{/if}

			{#if confirming && ready}
				<div
					role="group"
					aria-label="Confirm submission"
					class="mt-3 rounded border border-periwinkle-line bg-periwinkle p-3 text-sm text-periwinkle-ink"
				>
					<p>{confirmMessage}</p>
					<div class="mt-2 flex gap-2">
						<Button size="sm" onclick={submit}>Yes, submit</Button>
						<Button size="sm" variant="secondary" onclick={() => (confirming = false)}
							>Cancel</Button
						>
					</div>
				</div>
			{/if}

			<!-- On a narrow screen the grid scrolls sideways inside its panel, not the page. -->
			<div
				class="mt-3 overflow-x-auto rounded-2xl border border-line bg-surface p-3 shadow-sm"
				bind:clientWidth={width}
				data-pool-grid
			>
				<!-- Column headers. The sideboard is set apart by a rule. -->
				<div
					class="mb-2 grid gap-2"
					style="grid-template-columns: repeat({COLUMNS}, minmax(0, 1fr)); width:{inner}px"
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

				<div bind:this={gridEl} class="relative" style="height:{gridHeight}px; width:{inner}px">
					{#each layout as column, col (col)}
						{#if col === SIDEBOARD}
							<div
								class="absolute top-0 bottom-0 border-l border-dashed border-line-strong"
								style="left:{col * (colW + GAP) - GAP / 2}px"
							></div>
						{/if}
						{#each column as key, i (key)}
							{@const face = faces.get(key)!}
							{@const dragging = drag?.active && drag.key === key}
							<div
								class="absolute cursor-grab overflow-hidden rounded-[4.5%/3.2%] shadow-sm ring-focus select-none hover:ring-2 focus-visible:ring-2 focus-visible:outline-none [@media(pointer:fine)]:touch-none {dragging
									? 'opacity-30'
									: ''}"
								style="left:{col * (colW + GAP)}px; top:{i *
									strip}px; width:{colW}px; height:{cardH}px; z-index:{i + 1}"
								role="button"
								tabindex="0"
								data-key={key}
								data-col={col}
								aria-label="{face.name}, {col === SIDEBOARD
									? 'sideboard'
									: `deck, mana value ${HEADERS[col]}`}"
								title={face.basic
									? 'Double-click to remove'
									: `Double-click to move it to the ${col === SIDEBOARD ? 'deck' : 'sideboard'}`}
								onpointerdown={(e) => onpointerdown(e, key, col)}
								{onpointermove}
								{onpointerup}
								{onpointercancel}
								ondblclick={() => activate(key)}
								onkeydown={(e) => onkeydown(e, key, col, i)}
								oncontextmenu={(e) => toggleZoom(e, key, face.image, face.name)}
								onpointerleave={() => clearZoom(key)}
							>
								{#if face.image}
									<img src={face.image} alt="" draggable="false" class="h-full w-full" />
								{:else if face.basic}
									<div
										class="flex h-full w-full flex-col items-center p-1 text-center text-[11px] font-medium ring-1 ring-inset {basicFace(
											face.basic
										)}"
									>
										{face.name}
										<span class="mt-auto mb-auto text-3xl font-bold opacity-60">{face.basic}</span>
									</div>
								{:else}
									<div
										class="flex h-full w-full items-start justify-center bg-sunken p-1 text-center text-[11px] ring-1 ring-line"
									>
										{face.name}
									</div>
								{/if}
							</div>
						{/each}
					{/each}

					{#if drag?.active && target}
						<!-- Where the card will go. -->
						<div
							class="pointer-events-none absolute z-[60] h-1 rounded-full {target.allowed
								? 'bg-accent'
								: 'bg-danger-strong'}"
							style="left:{target.col * (colW + GAP)}px; width:{colW}px; top:{Math.max(
								0,
								target.index * strip - 3
							)}px"
						></div>
					{/if}
				</div>
			</div>
		</div>
	</div>
</section>

{#if drag?.active}
	{@const face = faces.get(drag.key)!}
	<!-- The card under the pointer while dragging. -->
	<div
		class="pointer-events-none fixed z-[70] overflow-hidden rounded-[4.5%/3.2%] shadow-2xl"
		style="left:{drag.x - drag.grabX}px; top:{drag.y -
			drag.grabY}px; width:{colW}px; height:{cardH}px"
	>
		{#if face.image}
			<img src={face.image} alt="" class="h-full w-full" />
		{:else}
			<div
				class="flex h-full w-full items-start justify-center p-1 text-center text-[11px] {face.basic
					? basicFace(face.basic)
					: 'bg-sunken'}"
			>
				{face.name}
			</div>
		{/if}
	</div>
{/if}

<ZoomLayer />
