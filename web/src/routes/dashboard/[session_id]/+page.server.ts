import { backend, orNotFound } from '#lib/dashboard/backend.server.ts';
import type { PageServerLoad } from './$types';

/** The steps are loaded too, so the trust panel can check the chain in the browser. */
export const load: PageServerLoad = async ({ fetch, params }) => {
	const steps = await orNotFound(backend(fetch).steps(params.session_id));
	return { steps };
};
