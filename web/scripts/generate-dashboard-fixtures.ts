/**
 * Writes the dashboard's mock audit events with a hash chain that really verifies (#50).
 *
 *   pnpm fixtures
 *
 * Output in src/lib/dashboard/fixtures/:
 *   d1042-events.json            order D-1042, 31 events (screens 31 to 33)
 *   d1042-events-tampered.json   the same, with event #17's payload edited afterwards
 *   d1042-transcript.json        the buyer and agent lines of D-1042
 *   live-call-events.json        the call still in progress on screen 30
 *   live-call-transcript.json
 *
 * Rerun after changing the hash format in src/lib/dashboard/hash.ts (`docs/audit-chain.md`).
 */
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { computeHash, formatAt, payloadHash, sha256Hex } from '../src/lib/dashboard/hash.ts';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '../src/lib/dashboard/fixtures');

type Localized = { en: string; fi: string };

interface Spec {
	at: string;
	actor: string;
	type: string;
	text: Localized;
	payload: Record<string, unknown>;
	quote_id?: string | null;
}

interface Session {
	session_id: string;
	channel: string;
	identity_masked: string | null;
	specs: Spec[];
}

const same = (text: string): Localized => ({ en: text, fi: text });
/** A Helsinki wall-clock time on the demo day, in the hashed form (`2026-11-12T08:02:14.000000Z`). */
const at = (time: string) => formatAt(new Date(`2026-11-12T${time}+02:00`));

const PHONE = '+358 40 *** **12';
const Q = 'q_7f3a';

const d1042: Session = {
	session_id: 's_2611_0042',
	channel: 'phone',
	identity_masked: PHONE,
	specs: [
		{
			at: at('10:02:14'),
			actor: 'relay',
			type: 'session_started',
			text: {
				en: 'Call started. Caller identified as Hassu Hauki Oy (returning). Kitchen avoids milk and nuts.',
				fi: 'Puhelu alkoi. Soittaja tunnistettiin: Hassu Hauki Oy (palaava). Keittiö välttää maitoa ja pähkinöitä.'
			},
			payload: {
				channel: 'phone',
				company: 'Hassu Hauki Oy',
				returning: true,
				exclusions: ['milk_free', 'nut_free'],
				identity_masked: PHONE,
				agent: 'gemini-voice',
				prompt_version: 'v7'
			}
		},
		{
			at: at('10:02:20'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"I need five kilos of ground beef for tomorrow."'),
			payload: { text: 'I need five kilos of ground beef for tomorrow.', lang: 'en', transcript: true }
		},
		{
			at: at('10:02:24'),
			actor: 'mcp',
			type: 'tool_called',
			text: {
				en: 'build_quote, 1 line: ground beef, 5 kg, needed by Sun 15 Nov',
				fi: 'build_quote, 1 rivi: jauheliha, 5 kg, tarvitaan su 15.11.'
			},
			payload: {
				call_id: 'call_1',
				tool: 'build_quote',
				summary: { en: '1 line: ground beef, 5 kg, needed by Sun 15 Nov', fi: '1 rivi: jauheliha, 5 kg, tarvitaan su 15.11.' },
				args: { lines: [{ text: 'ground beef', quantity: 5, unit: 'kg', needed_by: '2026-11-15' }] }
			}
		},
		{
			at: at('10:02:24'),
			actor: 'engine',
			type: 'clarification_asked',
			text: {
				en: 'Sunday is not a delivery day. Earliest is Mon 16 Nov.',
				fi: 'Sunnuntai ei ole toimituspäivä. Aikaisintaan ma 16.11.'
			},
			payload: { line_id: 'l1', reason_code: 'not_delivery_day', earliest: '2026-11-16' }
		},
		{
			at: at('10:02:24'),
			actor: 'mcp',
			type: 'tool_returned',
			text: same('needs_clarification'),
			payload: {
				call_id: 'call_1',
				tool: 'build_quote',
				result: {
					decision: 'needs_clarification',
					quote_id: Q,
					question_en: 'Sunday is not a delivery day. Is Monday 16 Nov fine?'
				}
			}
		},
		{
			at: at('10:02:27'),
			actor: 'agent',
			type: 'agent_said',
			text: same('"Tomorrow is Sunday. The earliest delivery is Monday. Is Monday fine?"'),
			payload: { text: 'Tomorrow is Sunday. The earliest delivery is Monday. Is Monday fine?', lang: 'en', transcript: true }
		},
		{
			at: at('10:02:33'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"Yes, Monday works."'),
			payload: { text: 'Yes, Monday works.', lang: 'en', transcript: true }
		},
		{
			at: at('10:02:34'),
			actor: 'mcp',
			type: 'tool_called',
			text: { en: 'update_quote, needed by Mon 16 Nov', fi: 'update_quote, tarvitaan ma 16.11.' },
			payload: {
				call_id: 'call_2',
				tool: 'update_quote',
				summary: { en: 'needed by Mon 16 Nov', fi: 'tarvitaan ma 16.11.' },
				args: { quote_id: Q, answer: { needed_by: '2026-11-16' } }
			}
		},
		{
			at: at('10:02:35'),
			actor: 'engine',
			type: 'products_searched',
			text: {
				en: 'Searched 17 546 products, 14 mince products match.',
				fi: 'Haettiin 17 546 tuotteesta, 14 jauhelihatuotetta sopii.'
			},
			payload: { line_id: 'l1', searched: 17546, matched: 14 }
		},
		{
			at: at('10:02:35'),
			actor: 'engine',
			type: 'candidates_filtered',
			text: {
				en: 'Removed 9: 4 arrive late, 3 out of stock, 2 contain milk.',
				fi: 'Poistettiin 9: 4 myöhässä, 3 loppu varastosta, 2 sisältää maitoa.'
			},
			payload: { line_id: 'l1', removed: { arrives_late: 4, out_of_stock: 3, contains_allergen: 2 }, left: 5 }
		},
		{
			at: at('10:02:35'),
			actor: 'engine',
			type: 'availability_checked',
			text: { en: 'Checked price and stock for 5 products.', fi: 'Tarkistettiin hinta ja saldo 5 tuotteelle.' },
			payload: { product_ids: ['801922', '801455', '802310', '806121', '801907'], source: 'snapshot' }
		},
		{
			at: at('10:02:36'),
			actor: 'engine',
			type: 'line_resolved',
			text: {
				en: 'Chose Beef mince 10 % 2,5 kg, 2 pcs = 5 kg, 41.90 €. Cheapest of 5 safe products that arrive Monday.',
				fi: 'Valittiin Naudan jauheliha 10 % 2,5 kg, 2 kpl = 5 kg, 41,90 €. Halvin 5 sopivasta tuotteesta, jotka ehtivät maanantaiksi.'
			},
			payload: { line_id: 'l1', product_id: '801922', quantity_sales_units: 2, line_total_cents: 4190, reason_codes: ['cheapest'] }
		},
		{
			at: at('10:02:36'),
			actor: 'mcp',
			type: 'tool_returned',
			text: same('ready'),
			payload: {
				call_id: 'call_2',
				tool: 'update_quote',
				result: {
					decision: 'ready',
					quote_id: Q,
					lines: 1,
					total_cents: 4190,
					say_en: 'I found beef mince 10 %, two 2.5 kg packs, 41.90 euros, arriving Monday.'
				}
			}
		},
		{
			at: at('10:02:38'),
			actor: 'agent',
			type: 'agent_said',
			text: same('"I found beef mince 10 %, two 2.5 kg packs, 41.90 euros, arriving Monday. Anything else?"'),
			payload: {
				text: 'I found beef mince 10 %, two 2.5 kg packs, 41.90 euros, arriving Monday. Anything else?',
				lang: 'en',
				transcript: true
			}
		},
		{
			at: at('10:02:49'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"Yes, my usual oat drink, twenty litres. And ten litres of rapeseed oil."'),
			payload: { text: 'Yes, my usual oat drink, twenty litres. And ten litres of rapeseed oil.', lang: 'en', transcript: true }
		},
		{
			at: at('10:02:51'),
			actor: 'mcp',
			type: 'tool_called',
			text: {
				en: 'update_quote, add 2 lines: usual oat drink 20 l, rapeseed oil 10 l',
				fi: 'update_quote, 2 riviä lisää: tavallinen kaurajuoma 20 l, rypsiöljy 10 l'
			},
			payload: {
				call_id: 'call_3',
				tool: 'update_quote',
				summary: {
					en: 'add 2 lines: usual oat drink 20 l, rapeseed oil 10 l',
					fi: '2 riviä lisää: tavallinen kaurajuoma 20 l, rypsiöljy 10 l'
				},
				args: {
					quote_id: Q,
					add_lines: [
						{ text: 'my usual oat drink', quantity: 20, unit: 'l', needed_by: '2026-11-16' },
						{ text: 'rapeseed oil', quantity: 10, unit: 'l', needed_by: '2026-11-16' }
					]
				}
			}
		},
		{
			at: at('10:02:52'),
			actor: 'engine',
			type: 'products_searched',
			text: {
				en: 'Searched 17 546 products: 6 oat drinks and 9 rapeseed oils match.',
				fi: 'Haettiin 17 546 tuotteesta: 6 kaurajuomaa ja 9 rypsiöljyä sopii.'
			},
			payload: { line_ids: ['l2', 'l3'], searched: 17546, matched: { l2: 6, l3: 9 } }
		},
		{
			at: at('10:02:52'),
			actor: 'engine',
			type: 'candidates_filtered',
			text: {
				en: 'Removed 7: 4 out of stock, 2 arrive late, 1 may contain nuts.',
				fi: 'Poistettiin 7: 4 loppu varastosta, 2 myöhässä, 1 voi sisältää pähkinöitä.'
			},
			payload: { line_ids: ['l2', 'l3'], removed: { out_of_stock: 4, arrives_late: 2, contains_allergen: 1 }, left: 8 }
		},
		{
			at: at('10:02:53'),
			actor: 'engine',
			type: 'line_resolved',
			text: {
				en: 'Chose Oat drink 1 l, 2 cases = 24 l, 51.60 €. The one this kitchen usually orders, rounded up from 20 l.',
				fi: 'Valittiin Kaurajuoma 1 l, 2 ltk = 24 l, 51,60 €. Keittiön tavallinen tuote, pyöristetty ylös 20 litrasta.'
			},
			payload: { line_id: 'l2', product_id: '465120', quantity_sales_units: 2, line_total_cents: 5160, reason_codes: ['usual', 'rounded_up'] }
		},
		{
			at: at('10:02:53'),
			actor: 'engine',
			type: 'line_resolved',
			text: {
				en: 'Chose Rapeseed oil 5 l, 2 pcs = 10 l, 34.90 €. Cheapest nut-free oil that arrives Monday.',
				fi: 'Valittiin Rypsiöljy 5 l, 2 kpl = 10 l, 34,90 €. Halvin pähkinätön öljy, joka ehtii maanantaiksi.'
			},
			payload: { line_id: 'l3', product_id: '412877', quantity_sales_units: 2, line_total_cents: 3490, reason_codes: ['cheapest'] }
		},
		{
			at: at('10:02:54'),
			actor: 'engine',
			type: 'quote_built',
			quote_id: Q,
			text: {
				en: 'Quote v1 ready: 3 lines, 128.40 € incl. VAT, 3 flags.',
				fi: 'Tarjous v1 valmis: 3 riviä, 128,40 € sis. ALV, 3 huomiota.'
			},
			payload: {
				quote_id: Q,
				version: 1,
				lines: 3,
				total_cents: 12840,
				flags: ['rounded_up', 'stock_unverified', 'no_allergen_info'],
				quote_hash: 'b51c0e6a2f1d9c7e4a3b8f20d6e1c9a75f3e2b8d4c6a1f09e7d3b5c2a8f4e610'
			}
		},
		{
			at: at('10:02:54'),
			actor: 'mcp',
			type: 'tool_returned',
			quote_id: Q,
			text: same('ready'),
			payload: {
				call_id: 'call_3',
				tool: 'update_quote',
				result: {
					decision: 'ready',
					quote_id: Q,
					version: 1,
					lines: 3,
					total_cents: 12840,
					flags: 3,
					say_en: 'Oat drink comes in cases of 12, so that is 24 litres. Rapeseed oil, two 5 litre cans.'
				}
			}
		},
		{
			at: at('10:03:02'),
			actor: 'agent',
			type: 'agent_said',
			text: same(
				'"Oat drink comes in cases of 12, so that is 24 litres. Rapeseed oil, two 5 litre cans. All together 128.40 euros, arriving Monday. Shall I send it to your phone for confirmation?"'
			),
			payload: {
				text: 'Oat drink comes in cases of 12, so that is 24 litres. Rapeseed oil, two 5 litre cans. All together 128.40 euros, arriving Monday. Shall I send it to your phone for confirmation?',
				lang: 'en',
				transcript: true
			}
		},
		{
			at: at('10:03:29'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"Yes, send it."'),
			payload: { text: 'Yes, send it.', lang: 'en', transcript: true }
		},
		{
			at: at('10:03:31'),
			actor: 'mcp',
			type: 'tool_called',
			quote_id: Q,
			text: {
				en: 'request_confirmation, quote q_7f3a v1, no recipient argument',
				fi: 'request_confirmation, tarjous q_7f3a v1, ei vastaanottaja-argumenttia'
			},
			payload: {
				call_id: 'call_4',
				tool: 'request_confirmation',
				summary: { en: 'quote q_7f3a v1, no recipient argument', fi: 'tarjous q_7f3a v1, ei vastaanottaja-argumenttia' },
				args: { quote_id: Q }
			}
		},
		{
			at: at('10:03:31'),
			actor: 'mcp',
			type: 'tool_returned',
			quote_id: Q,
			text: { en: 'SMS queued for end of call', fi: 'SMS jonossa puhelun loppuun' },
			payload: {
				call_id: 'call_4',
				tool: 'request_confirmation',
				result: {
					status: 'queued',
					deliver: 'end_of_call',
					label: { en: 'SMS queued for end of call', fi: 'SMS jonossa puhelun loppuun' }
				}
			}
		},
		{
			at: at('10:03:40'),
			actor: 'relay',
			type: 'session_ended',
			text: { en: 'Call ended by buyer after 1:26.', fi: 'Ostaja lopetti puhelun 1:26 jälkeen.' },
			payload: { ended_by: 'buyer', duration_s: 86 }
		},
		{
			at: at('10:03:41'),
			actor: 'confirmation',
			type: 'sms_sent',
			quote_id: Q,
			text: {
				en: `Link sent to the demo phone inbox and by SMS to ${PHONE}. Link shown on the call screen.`,
				fi: `Linkki lähetettiin demopuhelimen saapuneisiin ja tekstiviestinä numeroon ${PHONE}. Linkki näkyy puhelunäkymässä.`
			},
			payload: { to: PHONE, inbox: true, sms: true }
		},
		{
			at: at('10:03:52'),
			actor: 'confirmation',
			type: 'link_opened',
			quote_id: Q,
			text: { en: 'Buyer opened the link.', fi: 'Ostaja avasi linkin.' },
			payload: { quote_id: Q, version: 1 }
		},
		{
			at: at('10:04:05'),
			actor: 'confirmation',
			type: 'flags_acknowledged',
			quote_id: Q,
			text: { en: 'Buyer checked 3 flags (10:03 to 10:04).', fi: 'Ostaja tarkisti 3 huomiota (10.03–10.04).' },
			payload: {
				quote_id: Q,
				flags: [
					{ flag_key: 'rounded_up:l2', choice: 'keep_rounded', at: at('10:04:01') },
					{ flag_key: 'stock_unverified:l3', at: at('10:03:58') },
					{ flag_key: 'no_allergen_info:l3', at: at('10:04:05') }
				]
			}
		},
		{
			at: at('10:04:12'),
			actor: 'confirmation',
			type: 'order_confirmed',
			quote_id: Q,
			text: {
				en: 'Order confirmed. Stock rechecked: unchanged. Order D-1042 created.',
				fi: 'Tilaus vahvistettu. Saldo tarkistettiin uudelleen: ei muutoksia. Tilaus D-1042 luotu.'
			},
			payload: { quote_id: Q, version: 1, order_number: 'D-1042', stock_recheck: 'unchanged', total_cents: 12840 }
		}
	]
};

const liveCall: Session = {
	session_id: 's_2611_0043',
	channel: 'phone',
	identity_masked: PHONE,
	specs: [
		{
			at: at('10:41:02'),
			actor: 'relay',
			type: 'session_started',
			text: {
				en: 'Call started. Caller identified as Hassu Hauki Oy (returning). Kitchen avoids milk and nuts.',
				fi: 'Puhelu alkoi. Soittaja tunnistettiin: Hassu Hauki Oy (palaava). Keittiö välttää maitoa ja pähkinöitä.'
			},
			payload: { channel: 'phone', company: 'Hassu Hauki Oy', returning: true, identity_masked: PHONE, agent: 'gemini-voice', prompt_version: 'v7' }
		},
		{
			at: at('10:41:09'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"Five kilos of ground beef for Monday, and a few other things."'),
			payload: { text: 'Five kilos of ground beef for Monday, and a few other things.', lang: 'en', transcript: true }
		},
		{
			at: at('10:41:12'),
			actor: 'mcp',
			type: 'tool_called',
			text: { en: 'build_quote, 1 line: ground beef, 5 kg, needed by Mon 16 Nov', fi: 'build_quote, 1 rivi: jauheliha, 5 kg, tarvitaan ma 16.11.' },
			payload: {
				call_id: 'call_1',
				tool: 'build_quote',
				summary: { en: '1 line: ground beef, 5 kg, needed by Mon 16 Nov', fi: '1 rivi: jauheliha, 5 kg, tarvitaan ma 16.11.' },
				args: { lines: [{ text: 'ground beef', quantity: 5, unit: 'kg', needed_by: '2026-11-16' }] }
			}
		},
		{
			at: at('10:41:13'),
			actor: 'engine',
			type: 'line_resolved',
			text: {
				en: 'Chose Beef mince 10 % 2,5 kg, 2 pcs = 5 kg, 41.90 €. Cheapest of 5 safe products that arrive Monday.',
				fi: 'Valittiin Naudan jauheliha 10 % 2,5 kg, 2 kpl = 5 kg, 41,90 €. Halvin 5 sopivasta tuotteesta.'
			},
			payload: { line_id: 'l1', product_id: '801922', quantity_sales_units: 2, line_total_cents: 4190 }
		},
		{
			at: at('10:41:13'),
			actor: 'mcp',
			type: 'tool_returned',
			quote_id: 'q_8c21',
			text: same('ready'),
			payload: { call_id: 'call_1', tool: 'build_quote', result: { decision: 'ready', quote_id: 'q_8c21', lines: 1, total_cents: 4190 } }
		},
		{
			at: at('10:41:16'),
			actor: 'agent',
			type: 'agent_said',
			text: same('"Beef mince 10 %, two 2.5 kg packs for Monday. What else?"'),
			payload: { text: 'Beef mince 10 %, two 2.5 kg packs for Monday. What else?', lang: 'en', transcript: true }
		},
		{
			at: at('10:41:24'),
			actor: 'buyer',
			type: 'buyer_said',
			text: same('"Two kilos of butter, the lactose-free one."'),
			payload: { text: 'Two kilos of butter, the lactose-free one.', lang: 'en', transcript: true }
		},
		{
			at: at('10:41:26'),
			actor: 'mcp',
			type: 'tool_called',
			quote_id: 'q_8c21',
			text: { en: 'update_quote, add 1 line: lactose-free butter, 2 kg', fi: 'update_quote, 1 rivi lisää: laktoositon voi, 2 kg' },
			payload: {
				call_id: 'call_2',
				tool: 'update_quote',
				summary: { en: 'add 1 line: lactose-free butter, 2 kg', fi: '1 rivi lisää: laktoositon voi, 2 kg' },
				args: { quote_id: 'q_8c21', add_lines: [{ text: 'lactose-free butter', quantity: 2, unit: 'kg', needed_by: '2026-11-16' }] }
			}
		},
		{
			at: at('10:41:27'),
			actor: 'engine',
			type: 'products_searched',
			text: { en: 'Searched 17 546 products, 6 butter products match.', fi: 'Haettiin 17 546 tuotteesta, 6 voituotetta sopii.' },
			payload: { line_id: 'l2', searched: 17546, matched: 6 }
		},
		{
			at: at('10:41:27'),
			actor: 'engine',
			type: 'availability_checked',
			text: { en: 'Checking stock for 6 products.', fi: 'Tarkistetaan saldo 6 tuotteelle.' },
			payload: { product_ids: ['204001', '204002', '204010', '204017', '204022', '204031'], source: 'snapshot' }
		}
	]
};

interface Built extends Spec {
	seq: number;
	order_index: number;
	session_id: string;
	channel: string;
	identity_masked: string | null;
	payload_hash: string;
	prev_hash: string;
	session_prev_hash: string | null;
	hash: string;
}

/** Events from other sessions sit between these ones in the global chain. Not written out. */
const FILLERS_AFTER: Record<string, number[]> = {
	s_2611_0042: [7, 14, 24],
	s_2611_0043: [3, 6]
};

let seq = 1200;
let prevHash = await sha256Hex(new TextEncoder().encode('events before the fixtures'));

async function filler(): Promise<void> {
	seq++;
	const payload_hash = await sha256Hex(new TextEncoder().encode(`other session event ${seq}`));
	prevHash = await computeHash({
		prev_hash: prevHash,
		session_prev_hash: null,
		seq,
		at: at('10:00:00'),
		type: 'other',
		actor: 'system',
		session_id: null,
		quote_id: null,
		payload_hash
	});
}

async function build(session: Session): Promise<Built[]> {
	const out: Built[] = [];
	let sessionPrev: string | null = null;
	for (const [i, spec] of session.specs.entries()) {
		seq++;
		const quote_id = spec.quote_id ?? null;
		const payload_hash = await payloadHash(spec.payload, spec.text.fi, spec.text.en);
		const hash = await computeHash({
			prev_hash: prevHash,
			session_prev_hash: sessionPrev,
			seq,
			at: spec.at,
			type: spec.type,
			actor: spec.actor,
			session_id: session.session_id,
			quote_id,
			payload_hash
		});
		out.push({
			seq,
			order_index: i + 1,
			at: spec.at,
			actor: spec.actor,
			type: spec.type,
			text: spec.text,
			session_id: session.session_id,
			channel: session.channel,
			identity_masked: session.identity_masked,
			quote_id,
			payload: spec.payload,
			payload_hash,
			prev_hash: prevHash,
			session_prev_hash: sessionPrev,
			hash
		});
		prevHash = hash;
		sessionPrev = hash;
		if (FILLERS_AFTER[session.session_id]?.includes(i + 1)) {
			await filler();
			await filler();
		}
	}
	return out;
}

function transcriptOf(events: Built[]) {
	return events
		.filter((e) => e.type === 'buyer_said' || e.type === 'agent_said')
		.map((e) => ({
			// Transcript times aren't hashed, so they look like the API's datetimes: no
			// fractional seconds when there are none. Only steps keep the hashed six digits.
			at: e.at.replace(/\.0{6}Z$/, 'Z'),
			who: e.type === 'buyer_said' ? 'buyer' : 'agent',
			text: String(e.payload.text),
			lang: String(e.payload.lang ?? 'en')
		}));
}

function write(name: string, data: unknown): void {
	writeFileSync(join(OUT, name), `${JSON.stringify(data, null, '\t')}\n`);
	console.log(`wrote ${name}`);
}

const d1042Events = await build(d1042);
for (let n = 0; n < 5; n++) await filler();
const liveEvents = await build(liveCall);

// The tampered copy: event #17's payload is edited after the fact and its payload_hash
// recomputed, but the chain hash can't be fixed without the ones after it.
const tampered: Built[] = structuredClone(d1042Events);
const victim = tampered.find((e) => e.order_index === 17)!;
victim.payload = { ...victim.payload, matched: { l2: 2, l3: 9 } };
victim.text = {
	en: 'Searched 17 546 products: 2 oat drinks and 9 rapeseed oils match.',
	fi: 'Haettiin 17 546 tuotteesta: 2 kaurajuomaa ja 9 rypsiöljyä sopii.'
};
victim.payload_hash = await payloadHash(victim.payload, victim.text.fi, victim.text.en);

write('d1042-events.json', d1042Events);
write('d1042-events-tampered.json', tampered);
write('d1042-transcript.json', transcriptOf(d1042Events));
write('live-call-events.json', liveEvents);
write('live-call-transcript.json', transcriptOf(liveEvents));
