import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DeckBuilder from './DeckBuilder.svelte';
import type { PoolCard } from './model';

// 25 distinct creatures, so the deck can reach 40 with 15 basics.
const pool: PoolCard[] = Array.from({ length: 25 }, (_, i) => ({
	key: `k${i}`,
	id: `id${i}`,
	name: `Card ${String(i).padStart(2, '0')}`,
	manaCost: '{1}{G}',
	typeLine: 'Creature — Elf',
	cmc: (i % 5) + 1,
	colors: 'G'
}));

const count = () => page.getByText(/\d+ \/ 40/);
const submitButton = () => page.getByRole('button', { name: 'Submit deck' });

describe('DeckBuilder', () => {
	it('starts empty, with every card in the sideboard', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		await expect.element(count()).toHaveTextContent('0 / 40');
		await expect.element(submitButton()).toBeDisabled();
		await expect.element(page.getByText('Sideboard (25)')).toBeVisible();
	});

	it('moves a card to the deck on double-click, and back on another', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		await page.getByRole('button', { name: /Card 03/ }).dblClick();
		await expect.element(count()).toHaveTextContent('1 / 40');
		await expect.element(page.getByText('Sideboard (24)')).toBeVisible();

		await page.getByRole('button', { name: /Card 03/ }).dblClick();
		await expect.element(count()).toHaveTextContent('0 / 40');
	});

	it('moves a card with the keyboard alone, and keeps focus on a neighbour', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		const first = page.getByRole('button', { name: /Card 00/ });
		first.element().focus();
		await userEvent.keyboard('{Enter}');
		await expect.element(count()).toHaveTextContent('1 / 40');
		expect(document.activeElement?.hasAttribute('data-card')).toBe(true);
	});

	it('adds basics with the buttons and removes one on double-click', async () => {
		render(DeckBuilder, { pool, onSubmit: vi.fn() });
		const add = page.getByRole('button', { name: '+ Plains' });
		await add.click();
		await add.click();
		await expect.element(count()).toHaveTextContent('2 / 40');
		await expect.element(page.getByRole('button', { name: /Plains × 2/ })).toBeVisible();

		await page.getByRole('button', { name: /Plains × 2/ }).dblClick();
		await expect.element(count()).toHaveTextContent('1 / 40');
	});

	it('enables submit only at exactly 40, asks to confirm, then sends the deck', async () => {
		const onSubmit = vi.fn();
		render(DeckBuilder, { pool, onSubmit });
		for (const card of pool) {
			await page.getByRole('button', { name: new RegExp(card.name) }).dblClick();
		}
		const forest = page.getByRole('button', { name: '+ Forest' });
		for (let i = 0; i < 14; i++) await forest.click();
		await expect.element(count()).toHaveTextContent('39 / 40');
		await expect.element(submitButton()).toBeDisabled();

		await forest.click();
		await expect.element(count()).toHaveTextContent('40 / 40');
		await expect.element(submitButton()).toBeEnabled();

		await forest.click(); // 41: no longer submittable
		await expect.element(submitButton()).toBeDisabled();
		await page.getByRole('button', { name: /Forest × 16/ }).dblClick();

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
