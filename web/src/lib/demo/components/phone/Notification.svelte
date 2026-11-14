<script lang="ts">
	/** Phone-style notification from S.I.MO (design 13). Tapping it opens the message. */
	import { t } from '../../i18n';
	import type { Lang } from '../../types';

	let { lang, title, onopen }: { lang: Lang; title: string; onopen: () => void } = $props();
</script>

<button type="button" class="notif" data-testid="notification" onclick={onopen}>
	<span class="av" aria-hidden="true">S</span>
	<span class="text">
		<span class="meta"><span>S.I.MO</span><span>{t(lang, 'now')}</span></span>
		<span class="title">{title}</span>
		<span class="tap">{t(lang, 'notifTap')}</span>
	</span>
</button>

<style>
	.notif {
		width: 100%;
		display: flex;
		gap: 12px;
		align-items: center;
		text-align: left;
		color: var(--ink);
		background: #fff;
		border: 0;
		border-radius: 16px;
		padding: 14px;
		box-shadow:
			0 8px 24px rgba(16, 48, 63, 0.18),
			0 1px 3px rgba(16, 48, 63, 0.12);
		cursor: pointer;
		animation: drop 0.35s ease-out;
	}
	@keyframes drop {
		from {
			transform: translateY(-24px);
			opacity: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.notif {
			animation: none;
		}
	}
	.av {
		width: 44px;
		height: 44px;
		flex-shrink: 0;
		border-radius: 22px;
		background: var(--petrol);
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 24px;
		color: #fff;
	}
	.text {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
		min-width: 0;
	}
	.meta {
		display: flex;
		justify-content: space-between;
		font-size: 13px;
		color: var(--muted);
	}
	.title {
		font-weight: 700;
		font-size: 16px;
	}
	.tap {
		font-size: 14px;
		color: var(--muted);
	}
</style>
