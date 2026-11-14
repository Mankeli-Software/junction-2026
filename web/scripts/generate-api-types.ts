/** Writes src/lib/generated/openapi.ts from openapi.json: `pnpm gen:api-types`. */
import { writeFileSync } from 'node:fs';
import { renderApiTypes, TYPES_FILE } from './api-types.ts';

writeFileSync(TYPES_FILE, await renderApiTypes());
console.log(`wrote ${TYPES_FILE}`);
