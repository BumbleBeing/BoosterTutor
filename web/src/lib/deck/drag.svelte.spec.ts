import { afterEach, describe, expect, it, vi } from 'vitest';
import { DRAG_THRESHOLD, DragController, type DragOptions } from './drag.svelte';
import type { DropTarget } from './grid';

// A real element on the page for the controller to capture the pointer on,
// driven with synthetic pointer events.
let card: HTMLDivElement;

function setUp(target: DropTarget | null = { col: 4, index: 1, allowed: true }) {
	card = document.createElement('div');
	card.style.cssText = 'position:fixed; left:100px; top:50px; width:80px; height:110px';
	document.body.append(card);
	const options = {
		locate: vi.fn<DragOptions['locate']>(() => target),
		onStart: vi.fn(),
		onDrop: vi.fn<DragOptions['onDrop']>()
	};
	const drag = new DragController(options);
	// Only pointerdown needs the element (for currentTarget); the rest the card
	// would pass straight through, as GridCard does.
	card.addEventListener('pointerdown', (e) => drag.down(e, 'k1', 2));
	return { drag, options };
}

afterEach(() => card?.remove());

const pointer = (type: string, x: number, y: number, extra: PointerEventInit = {}) =>
	new PointerEvent(type, {
		bubbles: true,
		pointerId: 1,
		button: 0,
		clientX: x,
		clientY: y,
		...extra
	});

describe('DragController', () => {
	it('remembers where on the card it was grabbed, but is not a drag until it moves', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		expect(drag.dragging).toMatchObject({ key: 'k1', fromCol: 2, grabX: 10, grabY: 20 });
		expect(drag.activeKey).toBeNull();

		drag.move(pointer('pointermove', 110 + DRAG_THRESHOLD, 70)); // exactly the threshold: not yet
		expect(drag.activeKey).toBeNull();
		expect(options.onStart).not.toHaveBeenCalled();
		expect(options.locate).not.toHaveBeenCalled();
	});

	it('starts past the threshold, follows the pointer and reports where it would land', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.move(pointer('pointermove', 300, 90));
		expect(drag.activeKey).toBe('k1');
		expect(options.onStart).toHaveBeenCalledOnce();
		expect(drag.dragging).toMatchObject({ x: 300, y: 90 });
		expect(options.locate).toHaveBeenLastCalledWith(300, 90, 'k1', 2);
		expect(drag.target).toEqual({ col: 4, index: 1, allowed: true });

		drag.move(pointer('pointermove', 310, 95));
		expect(options.onStart).toHaveBeenCalledOnce(); // only once per drag
	});

	it('reports the move on release and then forgets the drag', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.move(pointer('pointermove', 300, 90));
		drag.up(pointer('pointerup', 320, 100));
		expect(options.locate).toHaveBeenLastCalledWith(320, 100, 'k1', 2);
		expect(options.onDrop).toHaveBeenCalledWith('k1', { col: 4, index: 1, allowed: true });
		expect(drag.dragging).toBeNull();
		expect(drag.target).toBeNull();
	});

	it('moves nothing on a click that never became a drag', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.up(pointer('pointerup', 111, 71));
		expect(options.onDrop).not.toHaveBeenCalled();
		expect(drag.dragging).toBeNull();
	});

	it('moves nothing when dropped where the card is not allowed', () => {
		const { drag, options } = setUp({ col: 8, index: 0, allowed: false });
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.move(pointer('pointermove', 300, 90));
		expect(drag.target?.allowed).toBe(false);
		drag.up(pointer('pointerup', 300, 90));
		expect(options.onDrop).not.toHaveBeenCalled();
	});

	it('moves nothing when the browser cancels the pointer', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.move(pointer('pointermove', 300, 90));
		drag.cancel();
		drag.up(pointer('pointerup', 300, 90));
		expect(drag.dragging).toBeNull();
		expect(options.onDrop).not.toHaveBeenCalled();
	});

	it('ignores other buttons and other pointers', () => {
		const { drag, options } = setUp();
		card.dispatchEvent(pointer('pointerdown', 110, 70, { button: 2 })); // right-click: zoom
		expect(drag.dragging).toBeNull();

		card.dispatchEvent(pointer('pointerdown', 110, 70));
		drag.move(pointer('pointermove', 300, 90, { pointerId: 2 })); // a second finger
		expect(drag.activeKey).toBeNull();
		drag.up(pointer('pointerup', 300, 90, { pointerId: 2 }));
		expect(drag.dragging).not.toBeNull();
		expect(options.onDrop).not.toHaveBeenCalled();
	});
});
