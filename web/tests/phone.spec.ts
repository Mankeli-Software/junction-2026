/**
 * The start page and the demo phone (issue #54) against the fixtures and the mock
 * voice relay (DEMO_SOURCE=fixture, mock/serve.ts). Chromium's fake microphone plays
 * tests/support/fake-voice.ts: silence, then a speech-like hum, over and over. The
 * mock relay takes each hum as the caller's next scripted line; the caller agrees to
 * the link on their second line.
 *
 * Every test types its own number, so each gets its own company and inbox.
 */
import { expect, test, type Page } from '@playwright/test';

function number(ending = ''): string {
	const digits = String(Math.floor(Math.random() * 1e7)).padStart(7, '0');
	return `40 ${(digits + ending).slice(-7)}`;
}

async function setUp(page: Page, phone = number(), kitchen: string[] = []) {
	await page.goto('/phone');
	await page.getByLabel('Your real phone number').fill(phone);
	for (const chip of kitchen) await page.getByRole('button', { name: chip, exact: true }).click();
	await page.getByRole('button', { name: 'Open demo phone' }).click();
	await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible();
}

const captions = (page: Page, who: 'agent' | 'buyer') => page.getByTestId(`caption-${who}`);
/** The activity indicator in one state. Short states are caught with waitFor, which polls every frame. */
const indicator = (page: Page, state: string) => page.locator(`[data-testid="indicator"][data-state="${state}"]`);

// The fake caller pauses 5.5 s between lines, so a scripted call takes a while.
test.describe.configure({ timeout: 60_000 });

test('start page leads to the demo phone', async ({ page, isMobile }) => {
	await page.goto('/');
	if (isMobile) {
		await expect(page.getByRole('heading', { name: 'Give S.I.MO a ring' })).toBeVisible();
		await page.getByRole('link', { name: /Call S\.I\.MO/ }).click();
	} else {
		await expect(page.getByRole('heading', { name: /Your kitchen order sorts itself out/ })).toBeVisible();
		await expect(page.getByRole('img', { name: 'QR code for the phone page' })).toBeVisible();
		await page.getByRole('link', { name: 'Call from this computer' }).click();
	}
	await expect(page).toHaveURL(/\/phone$/);
	await expect(page.getByRole('heading', { name: 'Your demo phone' })).toBeVisible();
	await expect(page.getByText('No real order is placed.', { exact: false })).toBeVisible();
	await expect(page.getByText('public demo dashboard', { exact: false })).toBeVisible();
});

test('the phone shows in a frame on a computer only', async ({ page, isMobile }) => {
	await page.goto('/phone');
	const aside = page.getByRole('heading', { name: 'This works best on your phone' });
	if (isMobile) await expect(aside).toBeHidden();
	else await expect(aside).toBeVisible();
});

test('call, captions, hang up, notification, inbox link opens the confirmation page', async ({ page }) => {
	await setUp(page, number(), ['Milk', 'Nuts']);
	await expect(page.getByTestId('company')).toHaveText(/ Oy$/);
	await expect(page.getByTestId('kitchen')).toHaveText('Avoids milk and nuts');
	await expect(page.getByText('Oat drink 1 l, Ground beef 10 % 2,5 kg, Rapeseed oil 5 l')).toBeVisible();

	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(page.getByTestId('in-call')).toBeVisible();
	await expect(page.getByText('Live captions, automatic')).toBeVisible();

	// The agent greets, the timer runs, the caller's lines arrive as captions.
	await expect(captions(page, 'agent').first()).toContainText('AI helper', { timeout: 10_000 });
	await expect(page.getByTestId('timer')).toHaveText(/^0:0\d$/);
	await indicator(page, 'listening').waitFor({ timeout: 10_000 });

	// After the caller's line: thinking, then checking products (build_quote), then speaking.
	await indicator(page, 'thinking').waitFor({ timeout: 15_000 });
	await expect(captions(page, 'buyer').first()).toContainText('five kilos of ground beef');
	await indicator(page, 'working').waitFor({ timeout: 5_000 });
	await expect(page.getByTestId('indicator')).toHaveText('Checking products...');
	await expect(page.getByTestId('agent-busy')).toHaveText('S.I.MO Checking products...');
	await indicator(page, 'speaking').waitFor({ timeout: 5_000 });
	await expect(page.getByTestId('agent-busy')).toHaveCount(0);
	await expect(captions(page, 'agent').nth(1)).toContainText('Shall I send the link', { timeout: 10_000 });

	// Before the link: preparing it (request_confirmation).
	await expect(captions(page, 'buyer').nth(1)).toContainText('Yes, send it.', { timeout: 15_000 });
	await indicator(page, 'working').waitFor({ timeout: 5_000 });
	await expect(page.getByTestId('indicator')).toHaveText('Preparing your order link...');
	await expect(captions(page, 'agent').nth(2)).toContainText('The link comes to your phone', { timeout: 10_000 });

	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('call-ended')).toBeVisible();
	await expect(page.getByTestId('ended-text')).toHaveText(/^Call ended, \d:\d\d$/);
	await expect(page.getByRole('heading', { name: 'Nothing is ordered yet' })).toBeVisible();
	await expect(page.getByTestId('sms-line')).toHaveCount(0);

	const notification = page.getByTestId('notification');
	await expect(notification).toContainText(/Confirm your order, 128,40\s€/);
	await notification.click();

	const message = page.getByTestId('inbox-message');
	await expect(message).toHaveCount(1);
	const link = message.getByRole('link');
	await expect(link).toHaveAttribute('href', /^\/c\/fx-ready-/);
	await link.click();

	await expect(page).toHaveURL(/\/c\/fx-ready-/);
	await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();

	// Back on the phone, the message is still in the inbox.
	await page.goBack();
	await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible();
	await page.getByRole('button', { name: /Messages/ }).click();
	await expect(page.getByTestId('inbox-message')).toHaveCount(1);
});

test('a vegan catering company starts vegan and can change it', async ({ page }) => {
	// The fixture makes a number ending in 0005 a vegan catering company (#81).
	await setUp(page, number('0005'));
	await expect(page.getByTestId('kitchen-type')).toHaveText('Vegan catering company');
	await expect(page.getByTestId('kitchen')).toHaveText('Avoids animal products');

	await page.getByRole('button', { name: 'Change kitchen' }).click();
	const vegan = page.getByRole('button', { name: 'Animal products', exact: true });
	await expect(vegan).toHaveAttribute('aria-pressed', 'true');
	await vegan.click();
	await page.getByRole('button', { name: 'Open demo phone' }).click();
	await expect(page.getByTestId('kitchen')).toHaveText('No restrictions');
});

test('hanging up before agreeing sends nothing', async ({ page }) => {
	await setUp(page);
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(captions(page, 'agent').first()).toContainText('What can I get you?', { timeout: 10_000 });
	await page.getByRole('button', { name: 'Hang up' }).click();

	await expect(page.getByTestId('no-order')).toHaveText('No order was made on this call.');
	await expect(page.getByTestId('notification')).toHaveCount(0);

	// Call again starts a new call for the same company.
	await page.getByRole('button', { name: 'Call S.I.MO again' }).click();
	await expect(page.getByTestId('in-call')).toBeVisible();
	await expect(captions(page, 'agent').first()).toContainText('AI helper', { timeout: 10_000 });
	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('call-ended')).toBeVisible();
});

test('mute and captions toggle during the call', async ({ page }) => {
	await setUp(page);
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(captions(page, 'agent').first()).toBeVisible({ timeout: 10_000 });

	const mute = page.getByRole('button', { name: 'Mute' });
	await mute.click();
	await expect(mute).toHaveAttribute('aria-pressed', 'true');
	await mute.click();
	await expect(mute).toHaveAttribute('aria-pressed', 'false');

	await page.getByRole('button', { name: 'Captions' }).click();
	await expect(page.getByText('Captions are off.')).toBeVisible();
	await page.getByRole('button', { name: 'Captions' }).click();
	await expect(captions(page, 'agent').first()).toBeVisible();

	await page.getByRole('button', { name: 'Speaker' }).click();
	await expect(page.getByText('Speaker off')).toBeVisible();

	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('call-ended')).toBeVisible();
});

test('a relay without agent_state still shows speaking and listening', async ({ page, context, baseURL }) => {
	await context.addCookies([{ name: 'simo_mock_agent_state', value: 'off', url: baseURL! }]);
	await setUp(page);
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();

	// Inferred from the audio the page plays: speaking during the greeting, then listening.
	await indicator(page, 'speaking').waitFor({ timeout: 10_000 });
	await expect(captions(page, 'agent').first()).toContainText('AI helper', { timeout: 10_000 });
	await indicator(page, 'listening').waitFor({ timeout: 10_000 });
	await expect(captions(page, 'buyer').first()).toContainText('five kilos', { timeout: 15_000 });
	await expect(captions(page, 'agent').nth(1)).toContainText('Shall I send the link', { timeout: 10_000 });
	await expect(page.getByTestId('agent-busy')).toHaveCount(0);
	await expect(indicator(page, 'thinking')).toHaveCount(0);

	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('call-ended')).toBeVisible();
});

test('the caller can talk over the agent', async ({ page }) => {
	// A microphone that stays quiet, then talks 1.3 s in, in the middle of the greeting.
	await page.addInitScript(() => {
		navigator.mediaDevices.getUserMedia = async () => {
			const context = new AudioContext();
			const tone = context.createOscillator();
			tone.frequency.value = 200;
			const gain = context.createGain();
			gain.gain.value = 0;
			tone.connect(gain);
			const out = context.createMediaStreamDestination();
			gain.connect(out);
			tone.start();
			setTimeout(() => gain.gain.setValueAtTime(0.5, context.currentTime), 1300);
			setTimeout(() => gain.gain.setValueAtTime(0, context.currentTime), 2500);
			return out.stream;
		};
	});
	await setUp(page);
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();

	// The greeting stops where the caller cut in, and the caller's line follows.
	await expect(captions(page, 'buyer').first()).toContainText('five kilos', { timeout: 10_000 });
	await expect(captions(page, 'agent').first()).not.toContainText('What can I get you?');
	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('call-ended')).toBeVisible();
});

test('an SMS line shows only when an SMS went out', async ({ page }) => {
	await setUp(page, number('7001'));
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(captions(page, 'agent').nth(2)).toContainText('The link comes to your phone', { timeout: 40_000 });
	await page.getByRole('button', { name: 'Hang up' }).click();
	await expect(page.getByTestId('sms-line')).toHaveText(/^Also sent by SMS to \+358 40 \*\*\* \*\*01$/);
	await expect(page.getByTestId('notification')).toBeVisible();
});

test('an invalid number is flagged on the field', async ({ page }) => {
	await page.goto('/phone');
	await page.getByLabel('Your real phone number').fill('12');
	await page.getByRole('button', { name: 'Open demo phone' }).click();
	await expect(page.getByRole('alert')).toContainText('Check the number');
	await expect(page.getByLabel('Your real phone number')).toHaveAttribute('aria-invalid', 'true');
});

test('a number over the demo limit is told to ask at the booth', async ({ page }) => {
	await page.goto('/phone');
	await page.getByLabel('Your real phone number').fill(number('0429'));
	await page.getByRole('button', { name: 'Open demo phone' }).click();
	await expect(page.getByRole('alert')).toHaveText(/reached the demo limit\. Ask us at the booth\./);
});

test('a denied microphone explains what to do', async ({ page }) => {
	await page.addInitScript(() => {
		navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('Denied', 'NotAllowedError'));
	});
	await setUp(page);
	await page.getByRole('button', { name: 'Call S.I.MO' }).click();
	await expect(page.getByTestId('call-failed')).toHaveAttribute('data-error', 'mic_denied');
	await expect(page.getByText('We need the microphone for the call.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('the phone page in Finnish', async ({ page }) => {
	await page.goto('/phone?lang=fi');
	await expect(page.getByRole('heading', { name: 'Demopuhelimesi' })).toBeVisible();
	await page.getByLabel('Oikea puhelinnumerosi').fill(number());
	await page.getByRole('button', { name: 'Avaa demopuhelin' }).click();
	await expect(page.getByRole('heading', { name: 'Yhteystiedot' })).toBeVisible();
	await page.getByRole('button', { name: 'Soita S.I.MOlle' }).click();
	await expect(captions(page, 'agent').first()).toContainText('tekoälyavustaja', { timeout: 10_000 });
	await page.getByRole('button', { name: 'Lopeta puhelu' }).click();
	await expect(page.getByText('Tässä puhelussa ei tehty tilausta.')).toBeVisible();
});
