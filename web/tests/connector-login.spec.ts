/**
 * The connector login pages (#48) against the fixture (DEMO_SOURCE=fixture): /signup,
 * /login with the phone step of a hand-out account, and the consent step on /connect.
 * In the fixture any `judge...@simo.mankeli.co` with `handout-pass` is a fresh hand-out
 * account, and Allow goes to `/phone?inbox=1&code=fixture`.
 */
import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'correct horse battery';

function unique(): string {
	return Math.random().toString(36).slice(2, 10);
}

function number(): string {
	return `40 ${String(Math.floor(Math.random() * 1e7)).padStart(7, '0')}`;
}

async function signUp(page: Page, email: string, password = PASSWORD) {
	await page.getByLabel('Email').fill(email);
	await page.getByLabel('Password').fill(password);
	await page.getByLabel('Your real phone number').fill(number());
	await page.getByRole('button', { name: 'Create account' }).click();
}

test('sign-up checks the fields, then opens the inbox on the phone page', async ({ page }) => {
	await page.goto('/signup');
	await expect(page.getByRole('heading', { name: 'Create an account' })).toBeVisible();

	await page.getByLabel('Email').fill('not an email');
	await page.getByLabel('Password').fill('short');
	await page.getByRole('button', { name: 'Create account' }).click();
	await expect(page.getByText('Check the email address.')).toBeVisible();
	await expect(page.getByText('Use at least 10 characters.')).toBeVisible();
	await expect(page.getByText(/Check the number/)).toBeVisible();

	await signUp(page, `chef-${unique()}@example.com`);
	await expect(page).toHaveURL(/\/phone\?inbox=1$/);
	await expect(page.getByRole('heading', { name: 'Messages' })).toBeVisible();
});

test('a taken email gets the neutral message', async ({ page }) => {
	const email = `chef-${unique()}@example.com`;
	await page.goto('/signup');
	await signUp(page, email);
	await expect(page).toHaveURL(/\/phone/);

	await page.context().clearCookies();
	await page.goto('/signup');
	await signUp(page, email);
	await expect(page.getByRole('alert')).toHaveText(/can't be used to sign up/);
});

test('wrong password, then a hand-out account sets its number and follows next', async ({ page }) => {
	const email = `judge${unique()}@simo.mankeli.co`;
	await page.goto(`/login?next=${encodeURIComponent('/connect?request=abc')}`);
	await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Create one' })).toHaveAttribute(
		'href',
		'/signup?next=%2Fconnect%3Frequest%3Dabc'
	);

	await page.getByLabel('Email').fill(email);
	await page.getByLabel('Password').fill('wrong password');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page.getByRole('alert')).toHaveText('Wrong email or password.');

	await page.getByLabel('Password').fill('handout-pass');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page.getByTestId('phone-step')).toBeVisible();
	await page.getByLabel('Your real phone number').fill(number());
	await page.getByRole('button', { name: 'Save and continue' }).click();

	await expect(page).toHaveURL(/\/connect\?request=abc$/);
	await expect(page.getByTestId('consent')).toContainText(/Allow Claude to order for .+ Oy\?/);
	await expect(page.getByTestId('consent')).toContainText('+358 40 *** **');
	await expect(page.getByTestId('consent')).toContainText('claude.ai');
	await page.getByRole('button', { name: 'Allow' }).click();
	await expect(page).toHaveURL(/code=fixture/);
});

test('the consent page sends a visitor without a session to log in and back', async ({ page }) => {
	await page.goto('/connect?request=xyz');
	await expect(page).toHaveURL(/\/login\?next=%2Fconnect%3Frequest%3Dxyz$/);

	await page.getByRole('link', { name: 'Create one' }).click();
	await expect(page).toHaveURL(/\/signup\?next=/);
	await signUp(page, `chef-${unique()}@example.com`);

	await expect(page).toHaveURL(/\/connect\?request=xyz$/);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await expect(page).toHaveURL(/error=access_denied/);
});

test('an expired request and an outside next are handled', async ({ page }) => {
	await page.goto('/signup?next=https%3A%2F%2Fevil.example%2F');
	await signUp(page, `chef-${unique()}@example.com`);
	await expect(page).toHaveURL(/\/phone\?inbox=1$/);

	await page.goto('/connect?request=expired');
	await expect(page.getByRole('alert')).toHaveText(/expired/);
});
