import { backend, orNotFound } from '#lib/dashboard/backend.server.ts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch, params }) => {
	const summary = await orNotFound(backend(fetch).summary(params.session_id));
	return { summary };
};
