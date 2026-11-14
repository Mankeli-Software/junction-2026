/**
 * The webshop's static products (#56): twelve real Valio products from the product
 * file, picked by scripts/select_shop_products.py into products.json. Name, pack
 * size, category and image only; prices and stock come through the agent tools.
 */
import file from './products.json';
import type { Text } from '#lib/demo/types.js';

export interface ShopProduct {
	product_id: string;
	name: Text;
	category: string;
	category_name: Text;
	shelf: string;
	pack_size: string | null;
	sales_unit: string;
	units_per_sales_unit: number;
	image_url: string | null;
}

export interface Shelf {
	key: string;
	name: Text;
}

export const SHELVES: Shelf[] = file.shelves;
export const PRODUCTS: ShopProduct[] = file.products;
