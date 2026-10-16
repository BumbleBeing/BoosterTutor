import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ReviewTimeline from './ReviewTimeline.svelte';
import { fixtureReview } from './fixture';

describe('ReviewTimeline', () => {
	it('loads no card images until a pick is expanded', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		expect(document.querySelectorAll('img')).toHaveLength(0);

		await page.getByRole('button', { name: /Beta Bear/ }).click();
		expect(document.querySelectorAll('img').length).toBeGreaterThan(0);
	});

	it('puts a marker only on Noted Picks and opens the sign-in prompt', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		const markers = page.getByRole('button', { name: /Coach's note/ });
		await expect.element(markers.first()).toBeInTheDocument();
		expect(document.querySelectorAll('[aria-label^="Coach"]')).toHaveLength(2);

		await markers.first().click();
		await expect.element(page.getByText("Sign in for a coach's note on this pick.")).toBeVisible();
	});

	it('labels the better card with the fitness that ranked it, and GIH WR beside it', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		// Pick 2 took Beta Bear (fitness 54.6); Alpha Knight was better (58.0, GIH WR 58.2%).
		const row = page.getByRole('button', { name: /Beta Bear/ }).element();
		const text = row.textContent?.replace(/\s+/g, ' ');
		expect(text).toContain('Better: Alpha Knight · fitness 58.0 vs 54.6 · GIH WR 58.2%');
	});

	it('shows what wheeled when its panel is opened', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		await page.getByText('What wheeled in pack 1').click();
		await expect.element(page.getByText('Pick 1 → pick 2')).toBeVisible();
		await expect.element(page.getByText('Good cards that came back: White 1.')).toBeVisible();
	});

	it('moves focus between picks with the arrow keys', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		const rows = document.querySelectorAll<HTMLElement>('[data-pick-toggle]');
		rows[0].focus();
		rows[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
		expect(document.activeElement).toBe(rows[1]);
	});

	it('keeps arrow keys inside its own timeline when there are two', async () => {
		const first = render(ReviewTimeline, { review: fixtureReview });
		render(ReviewTimeline, { review: fixtureReview });
		const own = first.container.querySelectorAll<HTMLElement>('[data-pick-toggle]');
		own[2].focus();
		own[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
		// The last row stays put; with a page-wide search it would jump to the second timeline.
		expect(document.activeElement).toBe(own[2]);
	});
});
