import { backend, orNotFound } from '#lib/dashboard/backend.server.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const api = backend(fetch);
	const id = params.session_id;
	const [steps, transcript, events] = await orNotFound(
		Promise.all([api.steps(id), api.transcript(id), api.events(id)])
	);
	return { steps, transcript, events };
};
