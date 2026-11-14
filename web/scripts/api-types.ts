/**
 * TypeScript types for /api/v1, generated with openapi-typescript from the OpenAPI
 * document that `uv run python -m app.interfaces.web_contract` writes in api/ (#56).
 * `pnpm gen:api-types` writes them; `api-types.test.ts` fails while they are stale.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString, type OpenAPI3 } from 'openapi-typescript';

const GENERATED = join(dirname(fileURLToPath(import.meta.url)), '../src/lib/generated');
export const OPENAPI_FILE = join(GENERATED, 'openapi.json');
export const TYPES_FILE = join(GENERATED, 'openapi.ts');

const HEADER = `/**
 * Generated from openapi.json by \`pnpm gen:api-types\` (scripts/api-types.ts). Do not edit.
 * openapi.json comes from \`uv run python -m app.interfaces.web_contract\` in api/.
 */

`;

export async function renderApiTypes(): Promise<string> {
	const document = JSON.parse(readFileSync(OPENAPI_FILE, 'utf8')) as OpenAPI3;
	return HEADER + astToString(await openapiTS(document));
}
