import { readFileSync } from 'node:fs';
import { expect, test } from 'vitest';
import { renderApiTypes, TYPES_FILE } from './api-types.ts';

test('the generated API types match openapi.json (run `pnpm gen:api-types`)', async () => {
	expect(readFileSync(TYPES_FILE, 'utf8')).toBe(await renderApiTypes());
});
