<script lang="ts">
	/**
	 * One product in the shop grid: picture, category, name, pack size and how it is
	 * sold. No price or stock: those come only through the agent tools (#56).
	 * Pictures are hotlinked without a Referer, with a placeholder when missing or broken
	 * (technical-plan.md §5.5).
	 */
	import Icon from '#lib/demo/components/Icon.svelte';
	import type { Lang } from '#lib/demo/types.js';
	import { t } from '../i18n';
	import type { ShopProduct } from '../products';

	let { product, lang }: { product: ShopProduct; lang: Lang } = $props();
	let broken = $state(false);
</script>

<article class="card" data-testid="product" data-product-id={product.product_id}>
	<div class="picture">
		{#if product.image_url && !broken}
			<img
				src={product.image_url}
				alt=""
				width="300"
				height="300"
				loading="lazy"
				referrerpolicy="no-referrer"
				onerror={() => (broken = true)}
			/>
		{:else}
			<span class="placeholder" title={t(lang, 'noImage')}>
				<Icon name="package" size={44} stroke="var(--petrol)" weight={1.6} />
			</span>
		{/if}
	</div>
	<div class="text">
		<span class="category">{product.category_name[lang]}</span>
		<h3>{product.name[lang]}</h3>
		<span class="pack">
			{#if product.pack_size}<b>{product.pack_size}</b>{/if}
			<span>
				{product.units_per_sales_unit > 1
					? t(lang, 'byCase', { n: product.units_per_sales_unit })
					: t(lang, 'byPiece')}
			</span>
		</span>
	</div>
</article>

<style>
	.card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 10px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.picture {
		aspect-ratio: 4 / 3;
		background: #fff;
		border-bottom: 1px solid var(--divider);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	img {
		width: 100%;
		height: 100%;
		object-fit: contain;
		padding: 12px;
	}
	.placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--chip);
	}
	.text {
		padding: 12px 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		flex-grow: 1;
	}
	.category {
		font-size: 13px;
		font-weight: 600;
		color: var(--muted);
	}
	h3 {
		margin: 0;
		font-size: 16px;
		line-height: 1.3;
		font-weight: 700;
		color: var(--ink);
		overflow-wrap: anywhere;
	}
	.pack {
		margin-top: auto;
		padding-top: 4px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 14px;
		color: var(--muted-2);
	}
	.pack b {
		font-size: 15px;
		color: var(--ink);
	}
</style>
