/**
 * The agent tools' REST twins (technical-plan.md §9.1) for the webshop's WebMCP tools
 * (#56), and the chat panel's paths (#57), when SvelteKit gets them. On the VM, Caddy sends `/api/*` to FastAPI and this
 * route is never reached. Locally, with DEMO_SOURCE=api, the request passes through to
 * FastAPI with the session cookie. With DEMO_SOURCE=fixture there is no engine to
 * answer, so the twins say so (the Playwright tests answer them with `page.route`).
 * Any other path under /api/v1 that has no route of its own is a 404.
 */
import { json, type RequestHandler } from '@sveltejs/kit';
import { AGENT_TOOLS } from '#lib/shop/webmcp.js';
import { demoSource, proxyToApi } from '#lib/server/demo/index.js';

const TWINS = AGENT_TOOLS.map((tool) => ({
	method: tool.rest.method,
	pattern: new RegExp(`^${tool.rest.path.replace(/\{\w+\}/g, '[^/]+')}$`)
}));

/**
 * The chat panel's own paths (#57, docs/plans/57-a2ui-chat.md §3): the chat streams, the
 * photo upload and what the cards load. Passed through the same way; the stream and the
 * multipart body go through as they are.
 */
const CHAT_PATHS: { method: string; pattern: RegExp }[] = [
	{ method: 'POST', pattern: /^\/api\/v1\/chat$/ },
	{ method: 'GET', pattern: /^\/api\/v1\/chat\/(menus\/[^/]+|sent\/latest)$/ },
	{ method: 'POST', pattern: /^\/api\/v1\/confirmations\/[^/]+\/chat$/ },
	{ method: 'GET', pattern: /^\/api\/v1\/quotes\/[^/]+$/ },
	{ method: 'POST', pattern: /^\/api\/v1\/recipe-drafts\/read$/ },
	{ method: 'GET', pattern: /^\/api\/v1\/recipe-drafts\/[^/]+$/ },
	{ method: 'POST', pattern: /^\/api\/v1\/recipe-drafts\/[^/]+\/(discard|copy)$/ }
];

const handler: RequestHandler = async (event) => {
	const method = event.request.method;
	const isTwin = [...TWINS, ...CHAT_PATHS].some(
		(twin) => twin.method === method && twin.pattern.test(event.url.pathname)
	);
	if (!isTwin) return json({ detail: 'Not Found' }, { status: 404 });
	if (demoSource() === 'api') return proxyToApi(event);
	return json(
		{ detail: 'The agent tools need FastAPI: start it and run the web app with DEMO_SOURCE=api.' },
		{ status: 503 }
	);
};

export const GET = handler;
export const POST = handler;
