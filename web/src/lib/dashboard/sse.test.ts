import { describe, expect, it } from 'vitest';
import recordedOverview from './fixtures/recorded/overview.json';
import recordedStream from './fixtures/recorded/stream.txt?raw';
import { applyOrderUpdated } from './merge';
import { ResumePoint, createSseParser, type SseMessage } from './sse';
import type { OverviewResponse, StreamMessage } from './types';

function parseAll(text: string, chunkSize = text.length): SseMessage[] {
	const out: SseMessage[] = [];
	const parser = createSseParser((m) => out.push(m));
	for (let i = 0; i < text.length; i += chunkSize) parser.push(text.slice(i, i + chunkSize));
	return out;
}

describe('createSseParser', () => {
	it('reads event, id and data, and skips comments', () => {
		const text = ': ping\n\nid: 7\nevent: step\ndata: {"a":1}\n\nevent: snapshot\ndata: {}\n\n';
		expect(parseAll(text)).toEqual([
			{ event: 'step', id: '7', data: '{"a":1}' },
			{ event: 'snapshot', id: null, data: '{}' }
		]);
	});

	it('joins data lines and accepts CRLF and CR line ends', () => {
		const text = 'event: x\r\ndata: one\r\ndata:two\r\r\n';
		expect(parseAll(text)).toEqual([{ event: 'x', id: null, data: 'one\ntwo' }]);
	});

	it('gives the same messages whatever the chunks', () => {
		const whole = parseAll(recordedStream);
		expect(parseAll(recordedStream, 1)).toEqual(whole);
		expect(parseAll(recordedStream.replaceAll('\r\n', '\n'), 7)).toEqual(whole);
	});

	it('keeps a half message until its blank line', () => {
		const out: SseMessage[] = [];
		const parser = createSseParser((m) => out.push(m));
		parser.push('id: 3\nevent: step\ndata: {}');
		expect(out).toEqual([]);
		parser.reset();
		parser.push('\n\nevent: snapshot\ndata: {}\n\n');
		expect(out).toEqual([{ event: 'snapshot', id: null, data: '{}' }]);
	});
});

describe('the recorded API stream', () => {
	const messages = parseAll(recordedStream);

	it('starts with a snapshot without an id and shares ids between events', () => {
		expect(messages[0]).toMatchObject({ event: 'snapshot', id: null });
		const updates = messages.filter((m) => m.event === 'order_updated');
		expect(updates.length).toBeGreaterThan(0);
		for (const update of updates) {
			expect(messages.some((m) => m.event === 'step' && m.id === update.id)).toBe(true);
			expect(JSON.parse(update.data).totals).toBeTruthy();
		}
	});

	it('ends in the same overview as GET /orders', () => {
		let overview = JSON.parse(messages[0].data) as OverviewResponse;
		const filter = { state: null, channel: null };
		for (const m of messages.slice(1)) {
			const message = { event: m.event, id: m.id, data: JSON.parse(m.data) } as StreamMessage;
			if (message.event === 'snapshot') overview = message.data;
			if (message.event === 'order_updated') applyOrderUpdated(overview, message.data, filter);
		}
		const expected = recordedOverview as OverviewResponse;
		expect(overview.totals).toEqual(expected.totals);
		expect(overview.companies).toEqual(expected.companies);
	});

	it('resumes from the id before the latest, so a split group comes again', () => {
		const resume = new ResumePoint();
		for (const m of messages) resume.seen(m.event, m.id);
		const ids = messages.map((m) => m.id).filter((id): id is string => id !== null);
		const last = ids[ids.length - 1];
		const beforeLast = [...new Set(ids)].at(-2);
		expect(resume.complete).toBe(beforeLast);
		expect(resume.complete).not.toBe(last);
	});
});

describe('ResumePoint', () => {
	it('takes a snapshot id as complete', () => {
		const resume = new ResumePoint();
		resume.seen('snapshot', '40');
		expect(resume.complete).toBe('40');
		resume.seen('step', '41');
		resume.seen('order_updated', '41');
		expect(resume.complete).toBe('40');
		resume.seen('step', '42');
		expect(resume.complete).toBe('41');
	});

	it('asks for a fresh snapshot after one without an id', () => {
		const resume = new ResumePoint();
		resume.seen('snapshot', null);
		resume.seen('step', '1');
		expect(resume.complete).toBeNull();
	});
});
