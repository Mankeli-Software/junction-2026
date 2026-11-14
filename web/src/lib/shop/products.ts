/**
 * The webshop's catalogue (#118): the category tree and a category's top products, as
 * FastAPI serves them at /api/v1/shop. Names, pack size and image only; prices and stock
 * come through the agent tools (#56).
 *
 * FIXTURE_PRODUCTS (products.json, written by scripts/select_shop_products.py) are twelve
 * real Valio products, the shop's stand-in catalogue with DEMO_SOURCE=fixture.
 */
import type { components } from '#lib/generated/openapi.js';
import type { Text } from '#lib/demo/types.js';
import file from './products.json';

export type ShopCatalogue = components['schemas']['ShopCatalogue'];
export type ShopSection = components['schemas']['ShopSection'];
export type ShopGroup = components['schemas']['ShopGroup'];
export type ShopCategory = components['schemas']['ShopCategory'];
export type ShopProduct = components['schemas']['ShopProduct'];
export type ShopProducts = components['schemas']['ShopProducts'];

interface FixtureProduct extends Omit<ShopProduct, 'brand'> {
	brand?: string | null;
	category: string;
	category_name: Text;
	shelf: string;
}

const SHELVES: { key: string; name: Text }[] = file.shelves;
export const FIXTURE_PRODUCTS = file.products as unknown as FixtureProduct[];

const FRESH: Text = { en: 'Fresh products', fi: 'Tuoretuotteet' };
const DRINKS: Text = { en: 'Drinks', fi: 'Juomat' };

/** The fixture as the API's tree: the shelves are the groups, juice under Drinks. */
export function fixtureCatalogue(): ShopCatalogue {
	const group = (key: string, name: Text): ShopGroup => {
		const categories = new Map<string, ShopCategory>();
		for (const product of FIXTURE_PRODUCTS.filter((p) => p.shelf === key)) {
			const known = categories.get(product.category);
			if (known) known.product_count += 1;
			else categories.set(product.category, { id: product.category, name: product.category_name, product_count: 1 });
		}
		return { name, categories: [...categories.values()] };
	};
	const groups = SHELVES.map((shelf) => ({ key: shelf.key, group: group(shelf.key, shelf.name) }));
	return {
		sections: [
			{ name: FRESH, groups: groups.filter((g) => g.key !== 'juice').map((g) => g.group) },
			{ name: DRINKS, groups: groups.filter((g) => g.key === 'juice').map((g) => g.group) }
		]
	};
}

/** Where a category sits in the tree, or null when the tree has no such category. */
export function findCategory(
	catalogue: ShopCatalogue,
	id: string
): { section: ShopSection; group: ShopGroup; category: ShopCategory } | null {
	for (const section of catalogue.sections) {
		for (const group of section.groups) {
			const category = group.categories.find((c) => c.id === id);
			if (category) return { section, group, category };
		}
	}
	return null;
}

export function firstCategory(catalogue: ShopCatalogue): string | null {
	return catalogue.sections[0]?.groups[0]?.categories[0]?.id ?? null;
}

export function fixtureProducts(id: string): ShopProducts | null {
	const place = findCategory(fixtureCatalogue(), id);
	if (!place) return null;
	return {
		section: place.section.name,
		group: place.group.name,
		category: place.category,
		products: FIXTURE_PRODUCTS.filter((p) => p.category === id).map(
			({ product_id, name, brand, pack_size, sales_unit, units_per_sales_unit, image_url }) => ({
				product_id,
				name,
				brand: brand ?? null,
				pack_size,
				sales_unit,
				units_per_sales_unit,
				image_url
			})
		)
	};
}
