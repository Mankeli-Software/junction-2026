/**
 * Client for the public dashboard endpoints (#49, `technical-plan.md` §9.5).
 *
 * The server-side `load` functions use it with `API_INTERNAL_URL`; the browser uses the
 * same-origin `/api/v1/...` through Caddy. With `PUBLIC_DASHBOARD_MOCK=1` the loads use
 * `mock/backend.ts` instead, which has the same interface.
 */
import type {
	AuditEvent,
	OrderSummary,
	OverviewFilter,
	OverviewResponse,
	Step,
	TranscriptLine
} from './types';

export const PUBLIC_API_PREFIX = '/api/v1/public';

export class NotFoundError extends Error {
	constructor(what: string) {
		super(`${what} not found`);
		this.name = 'NotFoundError';
	}
}

export interface DashboardApi {
	overview(filter: OverviewFilter): Promise<OverviewResponse>;
	summary(sessionId: string): Promise<OrderSummary>;
	steps(sessionId: string): Promise<Step[]>;
	transcript(sessionId: string): Promise<TranscriptLine[]>;
	events(sessionId: string): Promise<AuditEvent[]>;
}

/** `?state=&channel=` for the overview and the stream; empty filters are left out. */
export function filterQuery(filter: OverviewFilter): string {
	const params = new URLSearchParams();
	if (filter.state) params.set('state', filter.state);
	if (filter.channel) params.set('channel', filter.channel);
	const query = params.toString();
	return query ? `?${query}` : '';
}

function orderPath(sessionId: string, suffix = ''): string {
	return `${PUBLIC_API_PREFIX}/orders/${encodeURIComponent(sessionId)}${suffix}`;
}

export function eventsDownloadUrl(sessionId: string): string {
	return `${orderPath(sessionId, '/events')}?download=1`;
}

export function streamUrl(filter: OverviewFilter): string {
	return `${PUBLIC_API_PREFIX}/stream${filterQuery(filter)}`;
}

export function createApi(fetchFn: typeof fetch, baseUrl = ''): DashboardApi {
	async function get<T>(path: string, what: string): Promise<T> {
		const response = await fetchFn(`${baseUrl}${path}`, { headers: { accept: 'application/json' } });
		if (response.status === 404) throw new NotFoundError(what);
		if (!response.ok) throw new Error(`GET ${path} failed with ${response.status}`);
		return (await response.json()) as T;
	}

	return {
		overview: (filter) => get(`${PUBLIC_API_PREFIX}/orders${filterQuery(filter)}`, 'Orders'),
		summary: (id) => get(orderPath(id), 'Order'),
		steps: (id) => get(orderPath(id, '/steps'), 'Order'),
		transcript: (id) => get(orderPath(id, '/transcript'), 'Order'),
		events: (id) => get(orderPath(id, '/events'), 'Order')
	};
}
