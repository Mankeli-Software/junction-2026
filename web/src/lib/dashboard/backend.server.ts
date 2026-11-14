/** Picks the data source for the server-side `load` functions: FastAPI, or the mock fixtures. */
import { API_INTERNAL_URL } from '$app/env/private';
import { PUBLIC_DASHBOARD_MOCK } from '$app/env/public';
import { error } from '@sveltejs/kit';
import { NotFoundError, createApi, type DashboardApi } from './api';
import { mockApi } from './mock/backend';

export function backend(fetchFn: typeof fetch): DashboardApi {
	return PUBLIC_DASHBOARD_MOCK ? mockApi : createApi(fetchFn, API_INTERNAL_URL);
}

/** Turns the API's 404 into SvelteKit's, so the "Order not found" page shows. */
export async function orNotFound<T>(promise: Promise<T>): Promise<T> {
	try {
		return await promise;
	} catch (err) {
		if (err instanceof NotFoundError) error(404, err.message);
		throw err;
	}
}
