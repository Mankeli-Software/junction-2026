/**
 * Screenshots of the webshop (#56) for pull requests and reviews, saved to
 * docs/screenshots/shop/. Skipped in normal test runs; regenerate with
 *
 *   SCREENSHOTS=1 pnpm exec playwright test shop-screenshots
 */
import { expect, test, type Page } from '@playwright/test';
import { callTool, installWebMcpShim } from './support/webmcp-shim';

const OUT = '../docs/screenshots/shop';

test.skip(!process.env.SCREENSHOTS, 'Set SCREENSHOTS=1 to take screenshots');

async function shot(page: Page, project: string, name: string, fullPage = false) {
	await page.mouse.move(0, 0);
	await page.screenshot({ path: `${OUT}/${project}-${name}.png`, fullPage });
}

test.describe('English', () => {
	test.use({ locale: 'en-US' });

	test('shop screenshots', async ({ page }, info) => {
		const project = info.project.name;
		await installWebMcpShim(page);
		await page.route('**/api/v1/quotes', (route) =>
			route.fulfill({
				json: {
					quote_id: 'q-1',
					decision: 'ready',
					status: 'ready',
					lines: [{}, {}, {}],
					total_cents: 12840
				}
			})
		);
		await page.route('**/api/v1/quotes/*/confirmation-request', (route) =>
			route.fulfill({ json: { sent_to_masked: '+358 40 *** **12', sms_status: 'off', inbox: true } })
		);

		await page.goto('/shop');
		await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
		await shot(page, project, '01-shop-en', project === 'laptop');

		const identity = page.getByTestId('identity');
		await page.getByLabel('Your real phone number').fill('40 123 4512');
		await identity.getByRole('button', { name: 'Milk', exact: true }).click();
		await identity.scrollIntoViewIfNeeded();
		await shot(page, project, '03-number-entry');

		await page.getByRole('button', { name: 'Continue' }).click();
		await expect(page.getByTestId('company')).toHaveText(/ Oy$/);
		await callTool(page, 'build_quote', { lines: [] });
		await callTool(page, 'request_confirmation', { quote_id: 'q-1' });
		await expect(page.getByTestId('confirmation-notice')).toBeVisible();
		await page.evaluate(() => window.scrollTo(0, 0));
		if (project === 'laptop') {
			await shot(page, project, '04-confirmation-requested', true);
		} else {
			await page.getByTestId('confirmation-notice').scrollIntoViewIfNeeded();
			await shot(page, project, '04-confirmation-requested');
		}
	});
});

test.describe('Finnish', () => {
	test.use({ locale: 'fi-FI' });

	test('shop screenshots in Finnish', async ({ page }, info) => {
		const project = info.project.name;
		await installWebMcpShim(page);
		await page.goto('/shop');
		await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
		await shot(page, project, '02-shop-fi', project === 'laptop');
	});
});
