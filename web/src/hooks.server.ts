import type { Handle } from '@sveltejs/kit/hooks';

/**
 * The confirmation link carries its token in the path (/c/<token>), so those pages
 * never send a Referer (also towards image hosts), are never cached and never indexed
 * (technical-plan.md §8.3).
 */
export const handle: Handle = async ({ event, resolve }) => {
	const response = await resolve(event);
	if (event.url.pathname.startsWith('/c/')) {
		response.headers.set('Referrer-Policy', 'no-referrer');
		response.headers.set('Cache-Control', 'no-store');
		response.headers.set('X-Robots-Tag', 'noindex');
	}
	return response;
};
