/**
 * Screenshots of the start page and the demo phone for pull requests and reviews,
 * saved to docs/screenshots/phone/. Skipped in normal test runs; regenerate with
 *
 *   SCREENSHOTS=1 pnpm exec playwright test phone-screenshots
 */
import { expect, test, type Page } from '@playwright/test';

const OUT = '../docs/screenshots/phone';

test.skip(!process.env.SCREENSHOTS, 'Set SCREENSHOTS=1 to take screenshots');

async function shot(page: Page, project: string, name: string, fullPage = false) {
	await page.mouse.move(0, 0);
	await page.screenshot({ path: `${OUT}/${project}-${name}.png`, fullPage });
}

test('phone screenshots', async ({ page }, info) => {
	test.setTimeout(60_000);
	const project = info.project.name;

	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await shot(page, project, '00-start', true);

	await page.goto('/phone');
	await page.getByLabel('Your real phone number').fill('40 123 4512');
	await page.getByRole('button', { name: 'Milk', exact: true }).click();
	await page.getByRole('button', { name: 'Nuts', exact: true }).click();
	await shot(page, project, '10-setup');

	await page.getByRole('button', { name: 'Open demo phone' }).click();
	await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible();
	await shot(page, project, '11-contacts');

	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(page.getByTestId('caption-agent').nth(1)).toContainText('Shall I send the link', { timeout: 15_000 });
	await shot(page, project, '12-in-call');
	await expect(page.getByTestId('caption-agent').nth(2)).toContainText('The link comes', { timeout: 15_000 });

	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('notification')).toBeVisible();
	await page.waitForTimeout(500);
	await shot(page, project, '13-call-ended');

	await page.getByTestId('notification').click();
	await expect(page.getByTestId('inbox-message')).toBeVisible();
	await shot(page, project, '15-messages');
});
