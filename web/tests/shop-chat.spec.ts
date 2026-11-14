/**
 * S.I.MO's chat panel on the webshop (#57, docs/specs/webshop-chat.md §7) against a
 * scripted chat stream (tests/support/fake-chat.ts). The number entry and the session
 * are the demo fixture (DEMO_SOURCE=fixture); the chat, the photo upload and what the
 * cards load are answered with `page.route`.
 */
import { expect, test, type Page } from '@playwright/test';
import { card, draft, fakeChat, MENU_QUOTE, menu, MILK_QUOTE, RECIPE_QUOTE, turn } from './support/fake-chat';

function number(): string {
	return `40 ${String(Math.floor(Math.random() * 1e7)).padStart(7, '0')}`;
}

const panel = (page: Page) => page.getByTestId('chat-panel');

/** Opens the chat and signs in with its own number entry, avoiding nuts. */
async function openAndSignIn(page: Page) {
	await page.goto('/shop');
	await page.getByTestId('chat-launcher').click();
	await expect(panel(page)).toBeVisible();
	await expect(panel(page).getByText('public demo dashboard', { exact: false })).toBeVisible();
	await panel(page).getByLabel('Your real phone number').fill(number());
	await panel(page).getByRole('button', { name: 'Nuts', exact: true }).click();
	await panel(page).getByRole('button', { name: 'Start chatting' }).click();
	await expect(panel(page).getByTestId('chat-exclusions')).toHaveText('Avoids nuts');
	await expect(page.getByLabel('Message S.I.MO')).toBeFocused();
}

test('opens as a panel, moves focus in and closes with Escape', async ({ page }) => {
	await page.goto('/shop');
	await page.getByTestId('chat-launcher').click();
	await expect(panel(page)).toBeVisible();
	await expect(panel(page).getByRole('heading', { name: 'Who is ordering?' })).toBeVisible();
	// Focus is inside the panel.
	expect(await panel(page).evaluate((el) => el.contains(document.activeElement))).toBe(true);
	await page.keyboard.press('Escape');
	await expect(panel(page)).toBeHidden();
	await expect(page.getByTestId('chat-launcher')).toBeFocused();
});

test('order by text: quote card, send to my phone, sent notice, and never the link', async ({ page }) => {
	const fake = await fakeChat(
		page,
		(body, f) => {
			if (body.action?.name === 'send_for_confirmation') {
				return turn('Sent. Your link is at https://simo.mankeli.co/c/secret-token in the phone.', {
					tool: 'request_confirmation',
					cards: [card('sent', { component: 'SentNotice' })]
				});
			}
			f.current.value = MILK_QUOTE;
			return turn('Here is your milk for Monday.', {
				tool: 'build_quote',
				cards: [card('quote', { component: 'QuoteCard', quoteId: 'q-milk' })],
				quoteId: 'q-milk'
			});
		},
		{ quotes: [MILK_QUOTE] }
	);
	await openAndSignIn(page);

	// The example prompt sends itself.
	await panel(page).getByRole('button', { name: '1 000 l lactose-free milk by Monday' }).click();
	await expect(panel(page).getByTestId('chat-buyer')).toHaveText(/1 000 l lactose-free milk by Monday/);
	await expect(panel(page).getByTestId('chat-agent').first()).toHaveText(/Here is your milk for Monday\./);
	expect(fake.bodies[0]).toEqual({
		conversation_id: null,
		message: '1 000 l lactose-free milk by Monday',
		action: null,
		attachment_draft_id: null
	});

	// The quote card from the engine's data, and the current order refreshed after `done`.
	const quoteCard = panel(page).locator('[data-surface-id="quote"]');
	await expect(quoteCard).toContainText('Valio lactose-free milk 1 l');
	await expect(panel(page).getByTestId('current-order-total')).toHaveText(/1\s?290,00\s€/);

	await quoteCard.getByRole('button', { name: /Send to my phone/ }).click();
	await expect(panel(page).getByTestId('chat-action')).toHaveText(/Send it to my phone/);
	await expect(panel(page).locator('[data-surface-id="sent"]')).toContainText(/demo phone/i);
	expect(fake.bodies[1]).toMatchObject({
		conversation_id: 'conv-1',
		message: null,
		action: { name: 'send_for_confirmation', context: { quoteId: 'q-milk' } }
	});

	// No confirmation link anywhere in the panel: not in text, not as a link or button.
	await expect(panel(page).getByTestId('chat-agent').last()).toContainText('the link is in your demo phone');
	expect(await panel(page).innerHTML()).not.toContain('/c/');
	await expect(panel(page).getByRole('link', { name: /confirmation page/i })).toHaveCount(0);
	await expect(panel(page).getByRole('button', { name: /confirmation page/i })).toHaveCount(0);
});

test('weekly menu: swap a day, build the order', async ({ page }) => {
	let swapped = false;
	const fake = await fakeChat(
		page,
		(body, f) => {
			if (body.action?.name === 'menu_swap_day') {
				swapped = true;
				return turn('Wednesday is now a fish dish.', {
					tool: 'show_menu',
					cards: [card('menu', { component: 'MenuWeek', menuId: 'menu-1' })]
				});
			}
			if (body.action?.name === 'menu_build') {
				f.current.value = MENU_QUOTE;
				return turn('Here is the order for the week.', {
					tool: 'build_quote',
					cards: [card('menu-quote', { component: 'QuoteCard', quoteId: 'q-menu' })],
					quoteId: 'q-menu'
				});
			}
			return turn('Here is a milk-free week. Tap a day to swap it.', {
				tool: 'show_menu',
				cards: [card('menu', { component: 'MenuWeek', menuId: 'menu-1' })]
			});
		},
		{ quotes: [MENU_QUOTE], menu: () => menu(swapped) }
	);
	await openAndSignIn(page);

	await panel(page).getByRole('button', { name: 'Plan a lunch menu for next week, 80 people' }).click();
	const menuCard = panel(page).locator('[data-surface-id="menu"]');
	await expect(menuCard).toContainText('Chicken and vegetable curry');
	await expect(menuCard).toContainText('Pea soup and pancakes');
	// Each day shows its recipe's image from the API, lazy and without a Referer; Friday has none.
	const dayImages = menuCard.getByTestId('menu-day').locator('img');
	await expect(dayImages).toHaveCount(4);
	await expect(dayImages.first()).toHaveAttribute('referrerpolicy', 'no-referrer');
	await expect(dayImages.first()).toHaveAttribute('loading', 'lazy');
	await expect(menuCard.getByTestId('menu-day').last().locator('[data-testid="thumb"][data-empty="true"]')).toHaveCount(1);

	await menuCard.getByRole('button', { name: 'Swap Wednesday' }).click();
	await expect(panel(page).getByTestId('chat-action').last()).toHaveText(/Swap Wednesday/);
	expect(fake.bodies[1].action).toMatchObject({ name: 'menu_swap_day', context: { menuId: 'menu-1', day: 'wed' } });
	await expect(panel(page).getByTestId('chat-agent').last()).toHaveText(/Wednesday is now a fish dish\./);

	await panel(page).locator('[data-surface-id="menu"]').getByRole('button', { name: /Build order from this menu/ }).click();
	await expect(panel(page).getByTestId('chat-action').last()).toHaveText(/Build the order from this menu/);
	const quoteCard = panel(page).locator('[data-surface-id="menu-quote"]');
	await expect(quoteCard).toContainText('Chicken and vegetable curry');
	await expect(quoteCard).toContainText(/salt/);
	// The curry group shows its recipe image; the soup group has none and no placeholder.
	await expect(quoteCard.locator('.grp img')).toHaveCount(1);
	// Product thumbnails: an image for the oat base, the placeholder for the oil.
	await expect(quoteCard.getByTestId('quote-line').first().locator('img')).toHaveAttribute('src', /api\.valioaimo\.fi\/medias/);
	await expect(quoteCard.getByTestId('quote-line').last().locator('[data-testid="thumb"][data-empty="true"]')).toHaveCount(1);
	expect(fake.bodies[2].action).toMatchObject({ name: 'menu_build', context: { menuId: 'menu-1' } });
});

test('recipe photo: read, confirm the recipe, get a quote', async ({ page }) => {
	const fake = await fakeChat(
		page,
		(body, f) => {
			if (body.attachment_draft_id) {
				return turn('Here is what I read from your photo.', {
					cards: [card('draft', { component: 'RecipeDraftCard', draftId: body.attachment_draft_id })]
				});
			}
			if (body.action?.name === 'recipe_confirmed') {
				f.current.value = RECIPE_QUOTE;
				return turn('Here is your order for the pies.', {
					tool: 'build_quote',
					cards: [card('recipe-quote', { component: 'QuoteCard', quoteId: 'q-recipe' })],
					quoteId: 'q-recipe'
				});
			}
			return turn('Tell me more.');
		},
		{ quotes: [RECIPE_QUOTE], draft: () => draft() }
	);
	await openAndSignIn(page);
	await expect(panel(page).getByTestId('photo-hint')).toHaveText(/Photos are read once and not kept\./);

	await page.getByLabel('Message S.I.MO').fill('Karelian pies from my notebook, for 120 please.');
	await panel(page)
		.getByTestId('photo-input')
		.setInputFiles({ name: 'recipe.jpg', mimeType: 'image/jpeg', buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });

	await expect(panel(page).getByTestId('chat-photo')).toContainText('Karelian pies from my notebook, for 120 please.');
	await expect(panel(page).getByRole('img', { name: 'Your recipe photo' })).toBeVisible();
	const draftCard = panel(page).locator('[data-surface-id="draft"]');
	await expect(draftCard.getByLabel('Dish')).toHaveValue('Karjalanpiirakat');
	expect(fake.uploads).toHaveLength(1);
	expect(fake.bodies[0]).toEqual({
		conversation_id: null,
		message: 'Karelian pies from my notebook, for 120 please.',
		action: null,
		attachment_draft_id: 'd-1'
	});

	await draftCard.getByRole('button', { name: /Confirm recipe/ }).click();
	await expect(panel(page).getByTestId('chat-action').last()).toHaveText(/Recipe confirmed/);
	expect(fake.bodies[1].action).toMatchObject({ name: 'recipe_confirmed', context: { draftId: 'd-1' } });
	const quoteCard = panel(page).locator('[data-surface-id="recipe-quote"]');
	await expect(quoteCard).toContainText('Valio light milk 1 l');
	await expect(panel(page).getByTestId('current-order')).toBeVisible();
});

test('a photo that cannot be read gets a short plain sentence', async ({ page }) => {
	await page.route('**/api/v1/recipe-drafts/read', (route) => route.fulfill({ status: 422, json: { detail: 'No recipe' } }));
	await openAndSignIn(page);
	await panel(page)
		.getByTestId('photo-input')
		.setInputFiles({ name: 'cat.jpg', mimeType: 'image/jpeg', buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
	await expect(panel(page).getByTestId('chat-error')).toHaveText(
		'I could not read this photo. Try a sharper one, in good light, or type the ingredients.'
	);
});

test('without a chat model the panel says so calmly', async ({ page }) => {
	await page.route('**/api/v1/chat', (route) =>
		route.fulfill({ status: 503, json: { detail: { code: 'not_configured', message: 'Chat is not configured' } } })
	);
	await openAndSignIn(page);
	await page.getByLabel('Message S.I.MO').fill('My usual order');
	await page.keyboard.press('Enter');
	await expect(panel(page).getByTestId('chat-error')).toHaveText(/The chat is not set up right now\./);
	await expect(page.getByLabel('Message S.I.MO')).toBeEnabled();
});

test('Finnish follows the shop language', async ({ page }) => {
	await page.goto('/shop?lang=fi');
	await page.getByTestId('chat-launcher').click();
	await expect(panel(page).getByRole('heading', { name: 'Kuka tilaa?' })).toBeVisible();
	await expect(panel(page).getByRole('button', { name: 'Sulje chat' })).toBeVisible();
});

test.describe('at 390 px', () => {
	test.use({ viewport: { width: 390, height: 844 } });

	test('the panel is full screen and nothing overflows', async ({ page }) => {
		await fakeChat(page, (_, f) => {
			f.current.value = MILK_QUOTE;
			return turn('Here is your milk for Monday.', {
				cards: [card('quote', { component: 'QuoteCard', quoteId: 'q-milk' })],
				quoteId: 'q-milk'
			});
		}, { quotes: [MILK_QUOTE] });
		await openAndSignIn(page);
		await panel(page).getByRole('button', { name: 'My usual order' }).click();
		await expect(panel(page).locator('[data-surface-id="quote"]')).toContainText('Valio lactose-free milk 1 l');
		const box = await panel(page).boundingBox();
		expect(box).toMatchObject({ x: 0, y: 0, width: 390 });
		const overflow = await page.evaluate(() => {
			const root = document.querySelector('[data-testid="chat-panel"]')!;
			return [...root.querySelectorAll('*')].filter((el) => el.getBoundingClientRect().right > 391).map((el) => el.className);
		});
		expect(overflow).toEqual([]);
	});
});
