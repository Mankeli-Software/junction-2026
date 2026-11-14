import { backend, orNotFound } from '#lib/dashboard/backend.server.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const api = backend(fetch);
	const id = params.session_id;
	const [steps, events] = await orNotFound(Promise.all([api.steps(id), api.events(id)]));
	return { steps, events };
};
