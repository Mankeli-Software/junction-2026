import { describe, expect, it } from 'vitest';
import events from './fixtures/d1042-events.json';
import transcript from './fixtures/d1042-transcript.json';
import { buildTimeline, collapse, formatRefs, joinSentences, stepCount } from './timeline';
import type { AuditEvent, TranscriptLine } from './types';

describe('buildTimeline', () => {
	const rows = buildTimeline(events as AuditEvent[], events as AuditEvent[], transcript as TranscriptLine[]);
	const refs = rows.map((r) => formatRefs(r.refs));

	it('groups the steps as screen 32 does', () => {
		expect(refs.slice(0, 7)).toEqual(['#1', '#2', '#3–5', '#6', '#7', '#8, #13', '#9–11']);
		expect(refs.slice(-4)).toEqual(['#25–26', '#27–28', '#29–30', '#31']);
		expect(stepCount(rows)).toBe(31);
	});

	it('puts the tool arguments and the response in one box', () => {
		const box = rows[5];
		expect(box.kind).toBe('tool');
		if (box.kind !== 'tool') return;
		expect(box.tool).toBe('update_quote');
		expect(box.decision?.code).toBe('ready');
		expect(box.args).toEqual({ quote_id: 'q_7f3a', answer: { needed_by: '2026-11-16' } });
		expect((box.response as { total_cents: number }).total_cents).toBe(4190);
	});

	it('takes conversation text from the transcript', () => {
		const buyer = rows[1];
		expect(buyer.kind === 'buyer' && buyer.text).toBe('I need five kilos of ground beef for tomorrow.');
	});

	it('ends the sentences of a merged row', () => {
		expect(joinSentences(['Searched 12 products', 'Candidates filtered'])).toBe(
			'Searched 12 products. Candidates filtered'
		);
		expect(joinSentences(['Call ended by buyer.', 'Link sent.'])).toBe('Call ended by buyer. Link sent.');
		expect(joinSentences(['Conversation started'])).toBe('Conversation started');
	});

	it('collapses the middle of a long session', () => {
		const { head, hidden, tail } = collapse(rows);
		expect(head).toHaveLength(9);
		expect(tail).toHaveLength(4);
		expect(stepCount(hidden)).toBe(10);
	});
});
