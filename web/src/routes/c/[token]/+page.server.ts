/**
 * The confirmation page, server side: loads the view for the token and runs the
 * buyer's actions (acknowledge, edit, confirm, cancel) against the confirmation
 * source (fixture or FastAPI, see #lib/server/confirmation). Every action sends
 * the hash of the quote on screen, so a stale tab cannot act on an old version.
 *
 * Successful actions redirect back to the page (post, redirect, get), so a refresh
 * never repeats an action. Failures return the engine's text for the page to show.
 */
import { error, fail, redirect } from '@sveltejs/kit';
import { ConfirmationError, confirmationSource } from '#lib/server/confirmation/index.js';
import type { EditOp, Lang, Text } from '#lib/confirmation/types.js';
import type { Actions, PageServerLoad } from './$types';

export interface ActionFailureData {
	status: number;
	text: Text | null;
	lineId: string | null;
}

function langParam(url: URL): Lang | null {
	const lang = url.searchParams.get('lang');
	return lang === 'fi' || lang === 'en' ? lang : null;
}

export const load: PageServerLoad = async ({ params, url }) => {
	let view;
	try {
		view = await confirmationSource().get(params.token);
	} catch (e) {
		// The API failed or can't be reached: the generic error page, not an unexpected 500.
		if (e instanceof ConfirmationError) error(e.status >= 500 ? e.status : 503, 'unavailable');
		throw e;
	}
	if (!view) error(404, 'invalid');
	return {
		view,
		lang: langParam(url) ?? view.lang,
		lineId: url.searchParams.get('line'),
		askCancel: url.searchParams.has('cancel')
	};
};

/** The page URL to return to: the action parameter removed, and anything listed in `drop`. */
function back(url: URL, drop: string[] = []): string {
	const target = new URL(url);
	for (const key of [...target.searchParams.keys()]) {
		if (key.startsWith('/') || drop.includes(key)) target.searchParams.delete(key);
	}
	return target.pathname + target.search;
}

function field(form: FormData, name: string): string {
	const value = form.get(name);
	if (typeof value !== 'string' || value === '') error(400, `Missing ${name}`);
	return value;
}

async function run(url: URL, action: () => Promise<void>, drop: string[] = []) {
	try {
		await action();
	} catch (e) {
		if (e instanceof ConfirmationError) {
			if (e.status === 404) error(404, 'invalid');
			return fail(e.status, { status: e.status, text: e.text, lineId: e.lineId } satisfies ActionFailureData);
		}
		throw e;
	}
	redirect(303, back(url, drop));
}

/** The largest quantity a buyer can set on one line. */
const MAX_QUANTITY = 10_000;

function parseEdit(form: FormData): EditOp {
	const op = field(form, 'op');
	const lineId = field(form, 'line_id');
	if (op === 'set_quantity') {
		const quantity = Number(field(form, 'quantity'));
		if (!Number.isInteger(quantity) || quantity < 1 || quantity > MAX_QUANTITY) error(400, 'Bad quantity');
		return { op, line_id: lineId, quantity };
	}
	if (op === 'remove') return { op, line_id: lineId };
	if (op === 'choose_alternative') {
		return { op, line_id: lineId, alternative_id: field(form, 'alternative_id') };
	}
	error(400, 'Unknown edit');
}

export const actions: Actions = {
	acknowledge: async ({ params, request, url }) => {
		const form = await request.formData();
		const option = form.get('option_id');
		return run(url, () =>
			confirmationSource().acknowledge(
				params.token,
				field(form, 'quote_hash'),
				field(form, 'flag_key'),
				typeof option === 'string' && option !== '' ? option : null
			)
		);
	},

	edit: async ({ params, request, url }) => {
		const form = await request.formData();
		const edit = parseEdit(form);
		return run(
			url,
			() => confirmationSource().edit(params.token, field(form, 'quote_hash'), edit),
			edit.op === 'remove' ? ['line'] : []
		);
	},

	confirm: async ({ params, request, url }) => {
		const form = await request.formData();
		return run(url, () => confirmationSource().confirm(params.token, field(form, 'quote_hash')), [
			'line',
			'cancel'
		]);
	},

	cancel: async ({ params, request, url }) => {
		const form = await request.formData();
		return run(url, () => confirmationSource().cancel(params.token, field(form, 'quote_hash')), [
			'line',
			'cancel'
		]);
	}
};
