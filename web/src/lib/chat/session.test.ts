import { beforeAll, describe, expect, it } from 'vitest';
import { ChatSession, type TurnResult } from './session.svelte';

beforeAll(() => {
	URL.createObjectURL ??= () => 'blob:photo';
	URL.revokeObjectURL ??= () => {};
});

function sse(events: [string, unknown][]): Response {
	const text = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
	return new Response(text, { headers: { 'content-type': 'text/event-stream' } });
}

interface Sent {
	url: string;
	init: RequestInit;
}

function fake(answers: ((sent: Sent) => Response)[]) {
	const sent: Sent[] = [];
	const fetcher = (async (url: string, init: RequestInit) => {
		const call = { url, init };
		sent.push(call);
		const answer = answers.shift();
		if (!answer) throw new Error(`unexpected ${url}`);
		return answer(call);
	}) as typeof fetch;
	return { sent, fetcher };
}

const QUOTE_TURN = sse([
	['start', { conversation_id: 'c1' }],
	['tool', { name: 'build_quote', status: 'started' }],
	['tool', { name: 'build_quote', status: 'done' }],
	[
		'a2ui',
		{
			envelopes: [
				{ version: 'v0.9', createSurface: { surfaceId: 'q', catalogId: 'https://simo.mankeli.co/a2ui/catalog/v1.json' } },
				{ version: 'v0.9', updateComponents: { surfaceId: 'q', components: [{ id: 'root', component: 'QuoteCard', quoteId: 'q1' }] } }
			]
		}
	],
	['text', { delta: 'Here it is.' }],
	['done', { quote_id: 'q1' }]
]);

describe('ChatSession', () => {
	it('sends a message, fills the surface store and keeps the conversation id', async () => {
		const done: TurnResult[] = [];
		const { sent, fetcher } = fake([() => QUOTE_TURN, () => sse([['done', { quote_id: null }]])]);
		const session = new ChatSession({ endpoint: '/api/v1/chat', lang: () => 'en', fetcher, onDone: (r) => done.push(r) });

		await session.send('  1,000 L lactose-free milk by Monday ');
		expect(JSON.parse(String(sent[0].init.body))).toEqual({
			conversation_id: null,
			message: '1,000 L lactose-free milk by Monday',
			action: null,
			attachment_draft_id: null
		});
		expect(session.messages.map((m) => m.kind)).toEqual(['buyer', 'surface', 'agent']);
		expect(session.store.surfaces.q.components.root).toMatchObject({ component: 'QuoteCard', quoteId: 'q1' });
		expect(session.busy).toBe(false);
		expect(done).toEqual([{ quoteId: 'q1', quoteTouched: true }]);

		// A card action: echoed in plain words, posted as `action` with the conversation id.
		session.store.emit('q', 'root', 'send_for_confirmation', { quoteId: 'q1' });
		await Promise.resolve();
		await new Promise((r) => setTimeout(r, 0));
		const body = JSON.parse(String(sent[1].init.body));
		expect(body).toMatchObject({ conversation_id: 'c1', message: null, action: { name: 'send_for_confirmation', context: { quoteId: 'q1' } } });
		expect(session.messages.find((m) => m.kind === 'action')).toMatchObject({ text: 'Send it to my phone' });
	});

	it('reads a photo into a draft, then sends the turn with the draft attached', async () => {
		const { sent, fetcher } = fake([
			() => Response.json({ draft_id: 'd1' }),
			() => sse([['done', { quote_id: null }]])
		]);
		const session = new ChatSession({
			endpoint: '/api/v1/chat',
			photoEndpoint: '/api/v1/recipe-drafts/read',
			lang: () => 'en',
			fetcher
		});
		await session.sendPhoto(new File(['x'], 'recipe.jpg', { type: 'image/jpeg' }), 'Karelian pies, for 120 please.');
		expect(sent[0].url).toBe('/api/v1/recipe-drafts/read');
		const form = sent[0].init.body as FormData;
		expect(form.get('photo')).toBeInstanceOf(File);
		expect(form.get('portions')).toBe('120');
		expect(JSON.parse(String(sent[1].init.body))).toEqual({
			conversation_id: null,
			message: 'Karelian pies, for 120 please.',
			action: null,
			attachment_draft_id: 'd1'
		});
		expect(session.messages[0]).toMatchObject({ kind: 'photo', text: 'Karelian pies, for 120 please.' });
	});

	it('shows a reading error and sends no turn', async () => {
		const { sent, fetcher } = fake([() => new Response('{"detail":"No recipe"}', { status: 422 })]);
		const session = new ChatSession({ endpoint: '/api/v1/chat', photoEndpoint: '/read', lang: () => 'en', fetcher });
		await session.sendPhoto(new File(['x'], 'cat.jpg', { type: 'image/jpeg' }), '');
		expect(sent).toHaveLength(1);
		expect(session.messages.at(-1)).toMatchObject({ kind: 'error', key: 'read422' });
		expect(session.busy).toBe(false);
	});

	it('sends one turn at a time', async () => {
		let release: (r: Response) => void = () => {};
		const { sent, fetcher } = fake([() => new Promise<Response>((r) => (release = r)) as unknown as Response]);
		const session = new ChatSession({ endpoint: '/api/v1/chat', lang: () => 'en', fetcher });
		const first = session.send('one');
		expect(session.busy).toBe(true);
		await session.send('two');
		expect(sent).toHaveLength(1);
		release(sse([['done', { quote_id: null }]]));
		await first;
		expect(session.messages.filter((m) => m.kind === 'buyer')).toHaveLength(1);
	});
});
