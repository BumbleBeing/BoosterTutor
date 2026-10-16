import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DeckBuilder from './DeckBuilder.svelte';
import type { PoolCard } from './model';

// 25 cards with images, spread over mana values 0 to 4.
const pool: PoolCard[] = Array.from({ length: 25 }, (_, i) => ({
	key: `k${i}`,
	id: `id${i}`,
	name: `Card ${String(i).padStart(2, '0')}`,
	cmc: i % 5,
	image: 'data:image/gif;base64,R0lGODlhAQABAAAAACw='
}));

const count = () => page.getByText(/\d+ \/ 40/);
const submitButton = () => page.getByRole('button', { name: 'Submit deck' });
const cardButton = (name: string) => page.getByRole('button', { name: new RegExp(name) });

describe('DeckBuilder', () => {
	it('shows the pool as card images in nine columns, all in the deck to start', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		expect(document.querySelectorAll('[data-key] img')).toHaveLength(25);
		await expect.element(count()).toHaveTextContent('25 / 40');
		for (const header of ['0', '7+', 'Sideboard']) {
			await expect.element(page.getByText(header, { exact: true }).first()).toBeVisible();
		}
	});

	it('sends a card to the sideboard on double-click, and back on another', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		await cardButton('Card 03, deck').dblClick();
		await expect.element(count()).toHaveTextContent('24 / 40');
		await expect.element(cardButton('Card 03, sideboard')).toBeVisible();

		await cardButton('Card 03, sideboard').dblClick();
		await expect.element(count()).toHaveTextContent('25 / 40');
		await expect.element(cardButton('Card 03, deck, mana value 3')).toBeVisible();
	});

	it('moves a card with the keyboard alone and keeps focus on it', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		cardButton('Card 00, deck').element().focus();
		await userEvent.keyboard('{Enter}');
		await expect.element(count()).toHaveTextContent('24 / 40');
		expect(document.activeElement?.getAttribute('aria-label')).toContain('Card 00, sideboard');
	});

	it('drags a card to another column', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		const el = cardButton('Card 00, deck').element();
		const from = el.getBoundingClientRect();
		const gridRect = el.parentElement!.getBoundingClientRect();
		const fire = (type: string, x: number, y: number) =>
			el.dispatchEvent(
				new PointerEvent(type, {
					bubbles: true,
					pointerId: 1,
					button: 0,
					clientX: x,
					clientY: y
				})
			);
		fire('pointerdown', from.left + 5, from.top + 5);
		// Far to the right: the sideboard is the last ninth of the grid.
		fire('pointermove', gridRect.right - 5, from.top + 5);
		fire('pointerup', gridRect.right - 5, from.top + 5);
		await expect.element(cardButton('Card 00, sideboard')).toBeVisible();
	});

	it('adds basics with the buttons and removes one on double-click', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		const add = page.getByRole('button', { name: '+ Plains' });
		await add.click();
		await add.click();
		await expect.element(count()).toHaveTextContent('27 / 40');

		await page
			.getByRole('button', { name: /Plains, deck/ })
			.first()
			.dblClick();
		await expect.element(count()).toHaveTextContent('26 / 40');
	});

	it('shows a basic land with its set art when the set has it', async () => {
		const art = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
		render(DeckBuilder, { pool, basicImages: { W: art }, onSubmit: vi.fn() });
		const before = document.querySelectorAll('[data-key] img').length;
		await page.getByRole('button', { name: '+ Plains' }).click();
		await page.getByRole('button', { name: '+ Island' }).click(); // no art: drawn
		expect(document.querySelectorAll('[data-key] img').length).toBe(before + 1);
	});

	it('enables submit only at exactly 40, asks to confirm, then sends the deck', async () => {
		const onSubmit = vi.fn();
		render(DeckBuilder, { pool, onSubmit });
		const forest = page.getByRole('button', { name: '+ Forest' });
		for (let i = 0; i < 14; i++) await forest.click();
		await expect.element(count()).toHaveTextContent('39 / 40');
		await expect.element(submitButton()).toBeDisabled();

		await forest.click();
		await expect.element(count()).toHaveTextContent('40 / 40');
		await expect.element(submitButton()).toBeEnabled();

		await forest.click(); // 41: no longer submittable
		await expect.element(submitButton()).toBeDisabled();
		await page
			.getByRole('button', { name: /Forest, deck/ })
			.first()
			.dblClick();

		await submitButton().click();
		await expect
			.element(
				page.getByText('Only your first deck gets a written review. Later decks get ratings only.')
			)
			.toBeVisible();
		expect(onSubmit).not.toHaveBeenCalled();

		await page.getByRole('button', { name: 'Yes, submit' }).click();
		expect(onSubmit).toHaveBeenCalledOnce();
		const sent = onSubmit.mock.calls[0][0];
		expect(sent.cards).toHaveLength(25);
		expect(sent.basics).toEqual({ G: 15 });
	});
});
