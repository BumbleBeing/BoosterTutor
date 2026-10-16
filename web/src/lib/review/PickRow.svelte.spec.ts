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

	it('moves focus between picks with the arrow keys', async () => {
		render(ReviewTimeline, { review: fixtureReview });
		const rows = document.querySelectorAll<HTMLElement>('[data-pick-toggle]');
		rows[0].focus();
		rows[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
		expect(document.activeElement).toBe(rows[1]);
	});
});
