<script lang="ts">
	/**
	 * Sticky Confirm and Cancel (spec §4.5). Confirm stays disabled until every flag
	 * is acknowledged; the engine checks it again. Cancel asks once before it acts.
	 */
	import { enhance } from '$app/forms';
	import { money } from '../format';
	import { actionUrl, pageUrl, submitWithPending, ui, type PageUrl } from '../forms.svelte';
	import { t } from '../i18n';
	import type { ConfirmationView, Lang } from '../types';

	let { view, lang, url, askCancel }: { view: ConfirmationView; lang: Lang; url: PageUrl; askCancel: boolean } =
		$props();

	const remaining = $derived(view.flags.filter((f) => !f.acknowledged).length);
	const empty = $derived(view.requests.every((r) => r.lines.length === 0));
	const status = $derived(
		empty
			? t(lang, 'nothingLeft')
			: remaining === 1
				? t(lang, 'checksLeftOne')
				: remaining > 1
					? t(lang, 'checksLeft', { n: remaining })
					: t(lang, 'nothingUntilConfirm')
	);
</script>

<div class="bar">
	<div class="status">
		<span data-testid="confirm-status">{status}</span>
		<span>{t(lang, 'inclVat')}</span>
	</div>
	<form method="POST" action={actionUrl(url, 'confirm', ['lang'])} use:enhance={submitWithPending}>
		<input type="hidden" name="quote_hash" value={view.quote.hash} />
		<button class="hd confirm" disabled={remaining > 0 || empty || ui.pending}>
			{t(lang, 'confirm', { total: money(view.quote.total_cents) })}
		</button>
	</form>
	{#if askCancel}
		<div class="cancel-check" role="alertdialog" aria-labelledby="cancel-text">
			<p id="cancel-text">{t(lang, 'cancelCheck')}</p>
			<div class="cancel-actions">
				<a href={pageUrl(url, { cancel: null })} data-sveltekit-reset="false">{t(lang, 'cancelNo')}</a>
				<form method="POST" action={actionUrl(url, 'cancel', ['lang'])} use:enhance={submitWithPending}>
					<input type="hidden" name="quote_hash" value={view.quote.hash} />
					<button class="cancel-yes" disabled={ui.pending}>{t(lang, 'cancelYes')}</button>
				</form>
			</div>
		</div>
	{:else}
		<a class="cancel" href={pageUrl(url, { cancel: '1', line: null })} data-sveltekit-reset="false"
			>{t(lang, 'cancelOrder')}</a
		>
	{/if}
</div>

<style>
	.bar {
		position: sticky;
		bottom: 0;
		margin-top: 24px;
		background: var(--card);
		border-top: 1px solid var(--border);
		padding: 14px 16px 22px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		box-shadow: 0 -6px 18px rgba(16, 48, 63, 0.08);
		z-index: 10;
	}
	.status {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		font-size: 14px;
		color: var(--muted);
	}
	.confirm {
		width: 100%;
		height: 56px;
		border-radius: 8px;
		border: 0;
		background: var(--lime);
		color: var(--ink);
		font-size: 21px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		cursor: pointer;
	}
	.confirm:disabled {
		background: var(--lime-soft);
		color: var(--lime-text);
		cursor: not-allowed;
	}
	.cancel {
		align-self: center;
		font-size: 15px;
		font-weight: 600;
		padding: 6px;
	}
	.cancel-check {
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.cancel-check p {
		margin: 0;
		font-weight: 600;
	}
	.cancel-actions {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}
	.cancel-actions a {
		font-weight: 600;
	}
	.cancel-yes {
		height: 40px;
		padding: 0 16px;
		border-radius: 20px;
		border: 2px solid var(--red);
		background: var(--card);
		color: var(--red);
		font-weight: 700;
		cursor: pointer;
	}
</style>
