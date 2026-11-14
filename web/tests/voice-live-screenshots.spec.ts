/**
 * A real call through the phone page, the voice relay and Gemini Live (#52, #54), with
 * screenshots saved to docs/screenshots/phone-live/. Runs only with SCREENSHOTS=1 and
 * VOICE_LIVE_AUDIO, through playwright.voice-live.config.ts (see there).
 *
 * The caller's lines come from the fake microphone file: the whole order with "that's
 * all", then "kyllä" to the link. S.I.MO builds the quote, asks, sends the link and hangs
 * up; the link lands in the demo phone and opens the confirmation page.
 */
import { expect, test, type Page } from '@playwright/test';

const OUT = '../docs/screenshots/phone-live';

test.skip(!process.env.SCREENSHOTS || !process.env.VOICE_LIVE_AUDIO, 'Set SCREENSHOTS=1 and VOICE_LIVE_AUDIO');

async function shot(page: Page, project: string, name: string) {
	await page.mouse.move(0, 0);
	await page.screenshot({ path: `${OUT}/${project}-${name}.png` });
}

test('a real call', async ({ page }, info) => {
	test.setTimeout(240_000);
	const project = info.project.name;
	const number = `40 ${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;

	await page.goto('/phone?lang=fi');
	await page.getByLabel(/puhelinnumero/i).fill(number);
	await page.getByRole('button', { name: /avaa/i }).click();
	await expect(page.getByTestId('company')).toBeVisible();
	await page.getByRole('button', { name: 'Soita S.I.MOlle', exact: true }).click();

	// The greeting, then the caller's order and the quote.
	await expect(page.getByTestId('caption-agent').first()).toContainText('S.I.MO', { timeout: 20_000 });
	await expect(page.getByTestId('caption-buyer').first()).not.toBeEmpty({ timeout: 30_000 });
	// `working` lasts only as long as the tool, often a fraction of a second, so it is not
	// waited for here; the mock screenshots in docs/screenshots/phone/ show it.
	await expect(page.getByTestId('caption-agent').nth(1)).toContainText(/€|euro/i, { timeout: 40_000 });
	await page.locator('[data-testid="indicator"][data-state="listening"]').waitFor({ timeout: 40_000 });
	await shot(page, project, '12-in-call');

	// "Kyllä": the link, S.I.MO's goodbye and hang-up.
	await expect(page.getByTestId('notification')).toBeVisible({ timeout: 90_000 });
	await page.waitForTimeout(500);
	await shot(page, project, '13-call-ended');

	await page.getByTestId('notification').click();
	await expect(page.getByTestId('inbox-message')).toBeVisible();
	await shot(page, project, '15-messages');

	await page.getByTestId('inbox-message').getByRole('link').click();
	await page.waitForURL(/\/c\//);
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await page.waitForTimeout(1000);
	await shot(page, project, '20-confirmation');
});
