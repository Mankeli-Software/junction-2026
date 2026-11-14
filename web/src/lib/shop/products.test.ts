import { describe, expect, test } from 'vitest';
import { PRODUCTS } from './products';

describe('shop products', () => {
	// Valio's own image URLs from data/product_images.json.gz, hotlinked (#108).
	test.each(PRODUCTS.map((p) => [p.product_id, p.image_url]))('%s has a Valio image URL', (_, url) => {
		expect(url).toMatch(/^https:\/\/api\.valioaimo\.fi\/medias\//);
	});
});
