import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import type { MpEnrichedItem, MpItem, MpPayment } from '../../models/mercadopago.model';
import { MercadoPagoService } from '../../services/mercadopago.service';

const ML_SITE_HOSTS: Record<string, string> = {
  MLA: 'mercadolibre.com.ar',
  MLB: 'mercadolibre.com.br',
  MLC: 'mercadolibre.cl',
  MCO: 'mercadolibre.com.co',
  MLM: 'mercadolibre.com.mx',
  MLP: 'mercadolibre.com.pe',
  MLU: 'mercadolibre.com.uy',
  MLV: 'mercadolibre.com.ve',
};

function buildMlPermalink(id: string): string | null {
  if (!id) return null;
  const site = id.substring(0, 3).toUpperCase();
  const host = ML_SITE_HOSTS[site];
  return host ? `https://www.${host}/p/${id}` : null;
}

function stubToEnriched(stub: MpItem, fallbackCurrency: string | null): MpEnrichedItem {
  const id = String(stub.id ?? '');
  return {
    id,
    title: stub.title ?? null,
    quantity: stub.quantity ?? null,
    price: stub.unit_price != null ? Number(stub.unit_price) : null,
    currency_id: stub.currency_id ?? fallbackCurrency,
    condition: null,
    permalink: stub.title ? null : buildMlPermalink(id),
  };
}

@Component({
  selector: 'app-mercadopago-detail-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './mercadopago-detail-modal.component.html',
  styleUrl: './mercadopago-detail-modal.component.scss',
})
export class MercadoPagoDetailModalComponent {
  private readonly mpService = inject(MercadoPagoService);
  private readonly destroyRef = inject(DestroyRef);

  readonly payment = input<MpPayment | null>(null);
  readonly detailLoading = input(false);
  readonly idPrefix = input('mp-detail');

  readonly dismissed = output<void>();

  protected readonly showRawJson = signal(false);
  protected readonly enrichedItems = signal<MpEnrichedItem[]>([]);
  protected readonly itemsLoading = signal(false);

  protected readonly titleId = computed(() => `${this.idPrefix()}-mp-detail-title`);

  constructor() {
    effect(() => {
      const pmt = this.payment();
      untracked(() => {
        this.enrichedItems.set([]);
        this.itemsLoading.set(false);
        if (!pmt) {
          return;
        }
        const stubs = Array.isArray(pmt.additional_info?.items) ? pmt.additional_info!.items! : [];
        if (stubs.length === 0) {
          return;
        }

        // Items that already carry a title can be displayed without an extra fetch.
        const hasFullData = stubs.every((s) => s.title);
        if (hasFullData) {
          this.enrichedItems.set(stubs.map((s) => stubToEnriched(s, pmt.currency_id ?? null)));
          return;
        }

        // Stub-only items: attempt to fetch full details via the backend ML proxy.
        const ids = stubs.map((s) => String(s.id ?? '')).filter(Boolean);
        if (ids.length === 0) {
          return;
        }
        this.itemsLoading.set(true);
        this.mpService
          .getItems(ids)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (mlItems) => {
              const byId = new Map(mlItems.map((m) => [m.id ?? '', m]));
              this.enrichedItems.set(
                stubs.map((stub) => {
                  const detail = byId.get(String(stub.id ?? ''));
                  const id = String(stub.id ?? '');
                  return {
                    id,
                    title: detail?.title ?? stub.title ?? null,
                    quantity: stub.quantity ?? null,
                    price:
                      detail?.price ?? (stub.unit_price != null ? Number(stub.unit_price) : null),
                    currency_id: detail?.currency_id ?? stub.currency_id ?? pmt.currency_id ?? null,
                    condition: detail?.condition ?? null,
                    permalink: detail?.permalink ?? buildMlPermalink(id),
                  };
                }),
              );
              this.itemsLoading.set(false);
            },
            error: () => {
              // ML items API unavailable (token lacks scope) — show IDs with links.
              this.enrichedItems.set(stubs.map((s) => stubToEnriched(s, pmt.currency_id ?? null)));
              this.itemsLoading.set(false);
            },
          });
      });
    });
  }

  protected statusBadgeClass(status: string | null | undefined): string {
    const s = String(status ?? '').toLowerCase();
    if (s === 'approved') {
      return 'bg-emerald-500/15 text-emerald-800';
    }
    if (s === 'pending' || s === 'in_process') {
      return 'bg-amber-500/15 text-amber-950';
    }
    if (['rejected', 'cancelled', 'refunded'].includes(s)) {
      return 'bg-rose-500/15 text-rose-800';
    }
    return 'bg-surface-container text-on-surface-variant';
  }

  protected payerLabel(p: MpPayment): string | null {
    const pay = p.payer;
    if (!pay) {
      return null;
    }
    const name = `${pay.first_name ?? ''} ${pay.last_name ?? ''}`.trim();
    const email = pay.email?.trim() ?? '';
    if (email && name) {
      return `${name} (${email})`;
    }
    return email || name || pay.id?.toString() || null;
  }

  protected formatMoney(
    amount: number | null | undefined,
    currency?: string | null,
  ): string | null {
    if (amount == null || !Number.isFinite(amount)) {
      return null;
    }
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: (currency ?? 'USD').substring(0, 3),
        minimumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${amount.toFixed(2)} ${currency ?? ''}`.trim();
    }
  }

  protected displayQty(quantity: string | number | null | undefined): string {
    if (quantity == null || quantity === '') {
      return '—';
    }
    const n = Number(quantity);
    return Number.isFinite(n) ? String(n) : String(quantity);
  }

  protected toggleRaw(): void {
    this.showRawJson.update((v) => !v);
  }

  protected debugJson(row: MpPayment): string {
    return JSON.stringify(row, null, 2);
  }

  protected closeModal(): void {
    this.dismissed.emit();
  }
}
