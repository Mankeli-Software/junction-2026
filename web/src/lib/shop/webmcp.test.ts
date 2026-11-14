import { describe, expect, test, vi } from 'vitest';
import { AGENT_TOOLS, callTwin, registerAgentTools, type AgentTool, type WebMcpTool } from './webmcp';

const tool = (name: string) => AGENT_TOOLS.find((t) => t.name === name) as AgentTool;

function fakeFetch(status = 200, body: unknown = { ok: 1 }) {
	return vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(body), { status }));
}

test('the tools are exactly the ten agent tools, and nothing that confirms an order, cancels or reads the inbox', () => {
	expect(AGENT_TOOLS.map((t) => t.name)).toEqual([
		'search_products',
		'get_customer_context',
		'search_recipes',
		'get_recipe',
		'propose_recipe',
		'confirm_recipe',
		'build_quote',
		'update_quote',
		'request_confirmation',
		'get_order_status'
	]);
	for (const t of AGENT_TOOLS) {
		expect(t.description).toBeTruthy();
		expect(t.inputSchema.type).toBe('object');
		expect(t.rest.path).toMatch(/^\/api\/v1\//);
		expect(t.rest.path).not.toMatch(/private|inbox|cancel|confirmations/);
		// confirm_recipe confirms what was read from a recipe photo (#80), never an order: the
		// only /confirm path an agent may reach. Every other /confirm stays off limits.
		if (t.name !== 'confirm_recipe') expect(t.rest.path).not.toMatch(/\/confirm(\/|$)/);
	}
	expect(tool('confirm_recipe').rest.path).toBe('/api/v1/recipe-drafts/{draft_id}/confirm');
});

describe('callTwin', () => {
	test('GET puts the arguments in the query, lists repeated', async () => {
		const fetcher = fakeFetch();
		await callTwin(tool('search_products'), { q: 'maito', claims: ['lactose_free', 'vegan'], category: null }, fetcher);
		const [url, init] = fetcher.mock.calls[0];
		expect(url).toBe('/api/v1/products?q=maito&claims=lactose_free&claims=vegan');
		expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin' });
		expect(init?.body).toBeUndefined();
	});

	test('path parameters fill the path', async () => {
		const fetcher = fakeFetch();
		await callTwin(tool('get_recipe'), { recipe_id: 'r 1', portions: 80 }, fetcher);
		expect(fetcher.mock.calls[0][0]).toBe('/api/v1/recipes/r%201?portions=80');
	});

	test('POST sends the other arguments as JSON', async () => {
		const fetcher = fakeFetch();
		const lines = [{ line_id: 'l1', text: 'maito', quantity: 20, unit: 'l', needed_by: '2026-11-16' }];
		await callTwin(tool('update_quote'), { quote_id: 'q1', lines }, fetcher);
		const [url, init] = fetcher.mock.calls[0];
		expect(url).toBe('/api/v1/quotes/q1/update');
		expect(init).toMatchObject({ method: 'POST', credentials: 'same-origin' });
		expect(JSON.parse(String(init?.body))).toEqual({ lines });
	});

	test('a POST without other arguments has no body', async () => {
		const fetcher = fakeFetch();
		await callTwin(tool('request_confirmation'), { quote_id: 'q1' }, fetcher);
		const [url, init] = fetcher.mock.calls[0];
		expect(url).toBe('/api/v1/quotes/q1/confirmation-request');
		expect(init?.body).toBeUndefined();
	});

	test('a missing path parameter is an error without a request', async () => {
		const fetcher = fakeFetch();
		expect(await callTwin(tool('get_order_status'), {}, fetcher)).toMatchObject({ ok: false, status: 422 });
		expect(fetcher).not.toHaveBeenCalled();
	});
});

describe('registerAgentTools', () => {
	function fakeContext() {
		const tools = new Map<string, WebMcpTool>();
		return {
			tools,
			registerTool: vi.fn((t: WebMcpTool) => void tools.set(t.name, t)),
			unregisterTool: vi.fn((name: string) => void tools.delete(name))
		};
	}

	test('registers each tool with its generated name, description and schema', () => {
		const context = fakeContext();
		registerAgentTools(context);
		expect([...context.tools.keys()]).toEqual(AGENT_TOOLS.map((t) => t.name));
		const build = context.tools.get('build_quote');
		expect(build?.description).toBe(tool('build_quote').description);
		expect(build?.inputSchema).toEqual(tool('build_quote').inputSchema);
	});

	test('a result goes back as text and structured content, and to the page', async () => {
		const context = fakeContext();
		const onResult = vi.fn();
		registerAgentTools(context, onResult, fakeFetch(200, { sent_to_masked: '+358 40 *** **12' }));
		const result = await context.tools.get('request_confirmation')!.execute({ quote_id: 'q1' });
		expect(result.isError).toBeUndefined();
		expect(result.structuredContent).toEqual({ sent_to_masked: '+358 40 *** **12' });
		expect(JSON.parse(result.content[0].text)).toEqual({ sent_to_masked: '+358 40 *** **12' });
		expect(onResult).toHaveBeenCalledWith('request_confirmation', { sent_to_masked: '+358 40 *** **12' });
	});

	test('401 tells the agent the person has to enter their number', async () => {
		const context = fakeContext();
		registerAgentTools(context, () => {}, fakeFetch(401, { detail: 'Not signed in' }));
		const result = await context.tools.get('get_customer_context')!.execute({});
		expect(result.isError).toBe(true);
		expect(result.content[0].text).toMatch(/phone number on this page/);
	});

	test('the returned function removes the tools', () => {
		const context = fakeContext();
		const remove = registerAgentTools(context);
		remove();
		expect(context.tools.size).toBe(0);
	});
});
