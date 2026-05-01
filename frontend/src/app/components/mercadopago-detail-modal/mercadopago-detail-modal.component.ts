import { CommonModule } from '@angular/common';
import { Component, computed, input, output, signal } from '@angular/core';

import type { MpPayment } from '../../models/mercadopago.model';

@Component({
  selector: 'app-mercadopago-detail-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './mercadopago-detail-modal.component.html',
  styleUrl: './mercadopago-detail-modal.component.scss',
})
export class MercadoPagoDetailModalComponent {
  readonly payment = input<MpPayment | null>(null);
  readonly detailLoading = input(false);
  readonly idPrefix = input('mp-detail');

  readonly dismissed = output<void>();

  protected readonly showRawJson = signal(false);
  protected readonly titleId = computed(() => `${this.idPrefix()}-mp-detail-title`);

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

  protected formatMoney(amount: unknown, currency?: string | null): string | null {
    if (typeof amount !== 'number' || Number.isNaN(amount)) {
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
