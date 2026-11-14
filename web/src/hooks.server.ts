import type { Handle } from '@sveltejs/kit/hooks';

/**
 * The confirmation link carries its token in the path (/c/<token>), so those pages
 * never send a Referer to another site (for example the image host), are never cached
 * and never indexed (technical-plan.md §8.3).
 *
 * `same-origin` rather than `no-referrer`: with `no-referrer` the browser sends
 * `Origin: null` on a plain form post, and SvelteKit's CSRF check then refuses
 * every action when JavaScript is off. `same-origin` still keeps the token away
 * from every other origin.
 */
export const handle: Handle = async ({ event, resolve }) => {
	const response = await resolve(event);
	if (event.url.pathname.startsWith('/c/')) {
		response.headers.set('Referrer-Policy', 'same-origin');
		response.headers.set('Cache-Control', 'no-store');
		response.headers.set('X-Robots-Tag', 'noindex');
	}
	return response;
};
