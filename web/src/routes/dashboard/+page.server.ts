import { backend } from '#lib/dashboard/backend.server.ts';
import { parseFilter } from '#lib/dashboard/states.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }) => {
	const filter = parseFilter(url.searchParams);
	const overview = await backend(fetch).overview(filter);
	return { overview, filter };
};
