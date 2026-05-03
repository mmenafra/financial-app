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
import { finalize } from 'rxjs';

import type { MpPayment } from '../../models/mercadopago.model';
import { MercadoPagoService } from '../../services/mercadopago.service';
import { ToastService } from '../../services/toast.service';
import { httpErrorMessage } from '../../utils/transaction-edit';

const PAGE_SIZE = 30;

@Component({
  selector: 'app-visa-nacional-link-mercadopago-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './visa-nacional-link-mercadopago-modal.component.html',
  styleUrl: './visa-nacional-link-mercadopago-modal.component.scss',
})
export class VisaNacionalLinkMercadoPagoModalComponent {
  private readonly mpService = inject(MercadoPagoService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  readonly transactionId = input.required<string>();
  /** Optional subtitle (e.g. Visa row date + description). */
  readonly transactionLabel = input<string>('');

  readonly dismissed = output<void>();
  /** Emitted once after the link succeeds, before dismissed. Parent should refresh Visa data. */
  readonly linkedSuccess = output<void>();

  protected readonly rows = signal<MpPayment[]>([]);
  protected readonly listLoading = signal(false);
  protected readonly loadMoreLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly pagingTotal = signal<number | null>(null);
  protected readonly nextOffset = signal(0);
  protected readonly searchQuery = signal('');
  protected readonly linkingMpId = signal<string | null>(null);

  protected readonly titleId = 'vn-link-mp-title';

  protected readonly filteredRows = computed(() => {
    const q = this.searchQuery().trim().toLowerCase();
    const list = this.rows();
    if (!q) {
      return list;
    }
    return list.filter((row) => {
      const idStr = `${row.id ?? ''}`.toLowerCase();
      const desc = (row.description ?? '').toLowerCase();
      const dateStr = (row.date_created ?? '').toLowerCase();
      const amt = row.transaction_details?.total_paid_amount ?? row.transaction_amount ?? '';
      const amtStr = `${amt}`.toLowerCase();
      const stat = (row.status ?? '').toLowerCase();
      return (
        idStr.includes(q) ||
        desc.includes(q) ||
        dateStr.includes(q) ||
        amtStr.includes(q) ||
        stat.includes(q)
      );
    });
  });

  protected readonly hasMore = computed(() => {
    const total = this.pagingTotal();
    if (total == null) {
      return false;
    }
    return this.rows().length < total;
  });

  constructor() {
    effect(() => {
      this.transactionId();
      untracked(() => {
        this.searchQuery.set('');
        this.rows.set([]);
        this.pagingTotal.set(null);
        this.nextOffset.set(0);
        this.loadError.set(null);
        this.loadFirstPage();
      });
    });
  }

  protected closeModal(): void {
    this.dismissed.emit();
  }

  protected onSearchInput(event: Event): void {
    const v = (event.target as HTMLInputElement).value;
    this.searchQuery.set(v);
  }

  protected loadMore(): void {
    if (!this.hasMore() || this.listLoading()) {
      return;
    }
    this.fetchPage(true);
  }

  protected linkRow(mp: MpPayment, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    if (this.linkingMpId() != null) {
      return;
    }
    const rawId = mp.id;
    if (rawId == null || `${rawId}`.trim() === '') {
      this.toast.error('This payment does not include an ID.');
      return;
    }
    const idStr = `${rawId}`.trim();
    this.linkingMpId.set(idStr);
    this.mpService
      .linkToVisaTransaction(Number(idStr), this.transactionId())
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.linkingMpId.set(null)),
      )
      .subscribe({
        next: () => {
          this.toast.success('Mercado Pago payment linked');
          this.linkedSuccess.emit();
          this.dismissed.emit();
        },
        error: (err: unknown) => {
          this.toast.error(httpErrorMessage(err) ?? 'Could not create link.');
        },
      });
  }

  protected rowMenuKey(mp: MpPayment): string {
    const raw = mp.id;
    return raw == null ? '' : String(raw);
  }

  protected formatDisplayAmount(mp: MpPayment): string | null {
    const amount = mp.transaction_details?.total_paid_amount ?? mp.transaction_amount ?? null;
    const cur = mp.currency_id ?? 'CLP';
    if (typeof amount !== 'number' || Number.isNaN(amount)) {
      return null;
    }
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: String(cur ?? 'USD').substring(0, 3),
        minimumFractionDigits: cur === 'CLP' ? 0 : 2,
        maximumFractionDigits: cur === 'CLP' ? 0 : 2,
      }).format(amount);
    } catch {
      return `${amount} ${cur}`.trim();
    }
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

  private loadFirstPage(): void {
    this.rows.set([]);
    this.nextOffset.set(0);
    this.pagingTotal.set(null);
    this.fetchPage(false);
  }

  private fetchPage(append: boolean): void {
    const offset = append ? this.nextOffset() : 0;
    if (append) {
      this.loadMoreLoading.set(true);
    } else {
      this.listLoading.set(true);
    }
    this.loadError.set(null);

    this.mpService
      .getPayments(offset, PAGE_SIZE)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const chunk = res.results ?? [];
          if (append) {
            this.rows.update((existing) => [...existing, ...chunk]);
          } else {
            this.rows.set(chunk);
          }
          const total = res.paging?.total;
          this.pagingTotal.set(total != null ? Number(total) : null);
          this.nextOffset.set(offset + chunk.length);

          if (append) {
            this.loadMoreLoading.set(false);
          } else {
            this.listLoading.set(false);
          }
        },
        error: (err: unknown) => {
          if (append) {
            this.loadMoreLoading.set(false);
          } else {
            this.listLoading.set(false);
          }
          this.loadError.set(httpErrorMessage(err) ?? 'Could not load Mercado Pago payments.');
        },
      });
  }
}
