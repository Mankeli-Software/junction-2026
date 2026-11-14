import { describe, expect, it } from 'vitest';
import { channelBadge, connectorName, connectorNote } from './states';

describe('connector labels on a card', () => {
	it('names the connector in the badge and the note', () => {
		expect(connectorName('MCP Inspector')).toBe('MCP Inspector');
		expect(channelBadge('mcp', 'MCP Inspector', 'en')).toBe('MCP Inspector connector');
		expect(connectorNote('MCP Inspector', 'en')).toBe(
			"Conversation stays in the buyer's own app (MCP Inspector). Tool calls shown."
		);
		expect(connectorNote('Claude', 'fi')).toBe(
			'Keskustelu jää ostajan omaan sovellukseen (Claude). Työkalukutsut näytetään.'
		);
	});

	it('falls back when the connector gave no name', () => {
		expect(connectorName('MCP client')).toBeNull();
		expect(channelBadge('mcp', 'MCP client', 'en')).toBe('MCP connector');
		expect(connectorNote('MCP client', 'en')).toBe(
			"Conversation stays in the buyer's own app. Tool calls shown."
		);
	});
});
