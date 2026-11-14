import { describe, expect, test } from 'vitest';
import { FIXTURE_PRODUCTS, findCategory, firstCategory, fixtureCatalogue, fixtureProducts } from './products';

describe('shop products', () => {
	// Valio's own image URLs from data/product_images.json.gz, hotlinked (#108).
	test.each(FIXTURE_PRODUCTS.map((p) => [p.product_id, p.image_url]))('%s has a Valio image URL', (_, url) => {
		expect(url).toMatch(/^https:\/\/api\.valioaimo\.fi\/medias\//);
	});

	test('the fixture tree lists every fixture product once', () => {
		const catalogue = fixtureCatalogue();
		const categories = catalogue.sections.flatMap((s) => s.groups.flatMap((g) => g.categories));
		expect(categories.reduce((n, c) => n + c.product_count, 0)).toBe(FIXTURE_PRODUCTS.length);
		const first = firstCategory(catalogue);
		expect(first && findCategory(catalogue, first)?.section.name.en).toBe('Fresh products');
		for (const category of categories) {
			expect(fixtureProducts(category.id)?.products).toHaveLength(category.product_count);
		}
		expect(fixtureProducts('nope')).toBeNull();
	});
});
