/**
 * The dashboard on its mock (#50): the fixtures for screens 30 to 33 and the fake live
 * events, with PUBLIC_DASHBOARD_MOCK=1 (playwright.config.ts). tests/dashboard-api.spec.ts
 * runs the same pages against the real API. The dashboard targets computers, so only the
 * laptop profile runs these.
 */
import { expect, test } from '@playwright/test';

test.skip(!!process.env.E2E_API_URL, 'E2E_API_URL is set: the dashboard reads the API');
test.skip(({ isMobile }) => isMobile, 'The dashboard targets computers');

test('shows the overview and updates it live', async ({ page }) => {
	await page.goto('/dashboard');
	await expect(page.getByRole('heading', { name: 'Hassu Hauki Oy' })).toBeVisible();
	const d1042 = page.locator('a[href="/dashboard/s_2611_0042"]');
	await expect(d1042.getByTestId('order-number')).toHaveText('D-1042');
	// The live call's first scripted step, about 3.5 s in.
	await expect(page.getByText('Chose lactose-free butter, 4 pcs')).toBeVisible({ timeout: 10_000 });
});

test('opens an order and verifies its chain in the browser', async ({ page }) => {
	await page.goto('/dashboard/s_2611_0042');
	await expect(page.getByRole('heading', { name: 'Hassu Hauki Oy' })).toBeVisible();
	await expect(page.getByText('Order D-1042')).toBeVisible();
	await expect(page.getByText('Quote signed and verified')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Audit chain intact, 31 events' })).toBeVisible();
	await expect(page.getByTestId('ranked-not-available')).toHaveCount(0);

	await page.getByRole('link', { name: 'Full flow', exact: true }).click();
	await expect(page.getByText('update_quote').first()).toBeVisible();

	await page.getByRole('link', { name: 'Audit log', exact: true }).click();
	const status = page.getByRole('main').getByRole('status');
	await expect(status).toContainText('Chain intact');
	await expect(status).toContainText('31 events recomputed in your browser just now.');
	await page.getByRole('button', { name: 'Verify again' }).click();
	await expect(status).toContainText('Chain intact');
});

test('shows where a tampered chain breaks', async ({ page }) => {
	await page.goto('/dashboard/s_2611_0042_tampered/audit');
	await expect(page.getByRole('main').getByRole('status')).toContainText('Chain broken at event #17');
});

test('says an unsigned quote is not signed yet', async ({ page }) => {
	await page.goto('/dashboard/s_2611_0041');
	await expect(page.getByText('Quote not signed yet')).toBeVisible();
	await expect(page.getByText('Session s_2611_0041')).toBeVisible();
});
