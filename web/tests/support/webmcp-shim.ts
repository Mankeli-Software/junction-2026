/**
 * A stand-in for the browser's WebMCP model context, injected before the page's own
 * scripts. It records every `registerTool` call and lets a test call a tool the way a
 * browser agent would (`execute(input)`), through `window.__webmcp`.
 */
import type { Page } from '@playwright/test';

export interface RecordedTool {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
}

export interface ToolResult {
	content: { type: string; text: string }[];
	structuredContent?: unknown;
	isError?: boolean;
}

/** `where`: `document.modelContext` (current) or `navigator.modelContext` (the fallback). */
export async function installWebMcpShim(page: Page, where: 'document' | 'navigator' = 'document') {
	await page.addInitScript((target) => {
		type Tool = RecordedTool & { execute: (input: unknown) => Promise<unknown> };
		const tools = new Map<string, Tool>();
		const registered: string[] = [];
		const context = {
			registerTool(tool: Tool) {
				if (tools.has(tool.name)) throw new Error(`duplicate tool ${tool.name}`);
				tools.set(tool.name, tool);
				registered.push(tool.name);
			},
			unregisterTool(name: string) {
				tools.delete(name);
			}
		};
		Object.defineProperty(target === 'document' ? document : navigator, 'modelContext', {
			value: context,
			configurable: true
		});
		(window as unknown as { __webmcp: unknown }).__webmcp = {
			registered,
			tools: () => [...tools.values()].map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
			call: (name: string, input: unknown) => {
				const tool = tools.get(name);
				if (!tool) throw new Error(`no tool ${name}`);
				return tool.execute(input);
			}
		};
	}, where);
}

interface Shim {
	registered: string[];
	tools: () => RecordedTool[];
	call: (name: string, input: unknown) => Promise<ToolResult>;
}

export async function registeredTools(page: Page): Promise<RecordedTool[]> {
	return page.evaluate(() => (window as unknown as { __webmcp: Shim }).__webmcp.tools());
}

export async function callTool(page: Page, name: string, input: unknown): Promise<ToolResult> {
	return page.evaluate(
		([n, i]) => (window as unknown as { __webmcp: Shim }).__webmcp.call(n as string, i),
		[name, input] as const
	);
}
