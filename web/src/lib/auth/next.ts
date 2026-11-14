/**
 * The `next` parameter of /login and /signup (#48): where to go after logging in, usually
 * the connector consent page (`/connect?request=...`). Only a path on this site is
 * followed, so a crafted link can't send a fresh login to another site.
 */

/** Where the login pages go when there is no `next`: the phone page with the inbox. */
export const DEFAULT_NEXT = '/phone?inbox=1';

/** `raw` when it is a same-site path (`/...`, not `//...` or `/\...`), otherwise null. */
export function safeNext(raw: string | null | undefined): string | null {
	if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null;
	if (/[\u0000-\u001f\u007f]/.test(raw)) return null;
	try {
		const url = new URL(raw, 'http://same.invalid');
		return url.origin === 'http://same.invalid' ? url.pathname + url.search + url.hash : null;
	} catch {
		return null;
	}
}

/** `path` with `next` (and the language) carried along, e.g. the link from /login to /signup. */
export function withNext(path: string, next: string | null, lang: 'en' | 'fi' = 'en'): string {
	const params = new URLSearchParams();
	if (next) params.set('next', next);
	if (lang === 'fi') params.set('lang', 'fi');
	const query = params.toString();
	return query ? `${path}?${query}` : path;
}
