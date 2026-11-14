/**
 * Shared form behaviour for the confirmation page. Forms work without JavaScript;
 * with it, `submitWithPending` shows the "Checking your change..." state while the
 * engine works and always reloads the view afterwards, also after a refusal, so the
 * page shows the latest quote (for example after a requote).
 */
import type { SubmitFunction } from '$app/forms';

export const ui = $state({ pending: false });

/** The parts of the page URL the helpers need; `page.url` is read-only in Kit 3. */
export interface PageUrl {
	readonly href: string;
	readonly searchParams: { get(name: string): string | null };
}

export const submitWithPending: SubmitFunction = () => {
	ui.pending = true;
	return async ({ update }) => {
		try {
			await update({ refreshAll: true, reset: false });
		} finally {
			ui.pending = false;
		}
	};
};

/**
 * The URL a form posts to: `?/<action>` plus the page's own parameters (language,
 * open line), so a no-JavaScript submit comes back to the same view.
 */
export function actionUrl(url: PageUrl, action: string, keep: string[] = ['lang', 'line']): string {
	const params = keep
		.map((key) => [key, url.searchParams.get(key)] as const)
		.filter((entry): entry is readonly [string, string] => entry[1] !== null)
		.map(([key, value]) => `&${key}=${encodeURIComponent(value)}`)
		.join('');
	return `?/${action}${params}`;
}

/** A link to the same page with some parameters set or removed. */
export function pageUrl(url: PageUrl, set: Record<string, string | null>): string {
	const target = new URL(url.href);
	for (const [key, value] of Object.entries(set)) {
		if (value === null) target.searchParams.delete(key);
		else target.searchParams.set(key, value);
	}
	return target.pathname + target.search;
}
