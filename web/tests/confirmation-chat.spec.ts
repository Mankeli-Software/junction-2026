/**
 * "Ask for changes" on the confirmation page (#57, docs/specs/webshop-chat.md §5),
 * against the confirmation fixture and a scripted chat stream. After a turn that
 * changed the quote, the page reloads its view as after an edit with its own controls.
 */
import { expect, test } from '@playwright/test';
import { sse } from './support/fake-chat';

function token(scenario: string): string {
	return `fx-${scenario}-${Math.random().toString(36).slice(2, 10)}`;
}

test('asks for a change in words, reloads the view, and Confirm stays the page button', async ({ page }) => {
	const t = token('ready');
	const bodies: unknown[] = [];
	await page.route(`**/api/v1/confirmations/${t}/chat`, async (route) => {
		bodies.push(route.request().postDataJSON());
		await route.fulfill({
			headers: { 'content-type': 'text/event-stream' },
			body: sse([
				['start', { conversation_id: 'conv-c' }],
				['tool', { name: 'update_quote', status: 'started' }],
				['tool', { name: 'update_quote', status: 'done' }],
				['text', { delta: 'Done, it is 150 portions now.' }],
				['done', { quote_id: 'q-new' }]
			])
		});
	});
	await page.goto(`/c/${t}`);
	const ask = page.getByTestId('ask-for-changes');
	await ask.getByRole('button', { name: 'Ask for changes' }).click();
	await expect(page.getByLabel('Message S.I.MO')).toBeFocused();
	await expect(ask).toContainText('You still confirm with the button on this page.');

	const reload = page.waitForRequest((request) => request.url().includes('__data.json'));
	await page.getByLabel('Message S.I.MO').fill('Make it 150 portions');
	await page.keyboard.press('Enter');
	await expect(ask.getByTestId('chat-agent')).toHaveText(/150 portions now/);
	await reload;
	expect(bodies[0]).toEqual({ conversation_id: null, message: 'Make it 150 portions', action: null, attachment_draft_id: null });

	// The chat has no photo button and nothing that confirms; the page's Confirm is still there.
	await expect(ask.getByRole('button', { name: /confirm/i })).toHaveCount(0);
	await expect(ask.getByRole('button', { name: 'Add a recipe photo' })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /confirm/i })).toHaveCount(1);
});
