import { CommonModule } from '@angular/common';
import {
  Component,
  computed,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { MercadoPagoDetailModalComponent } from '../../components/mercadopago-detail-modal/mercadopago-detail-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { MpPayment } from '../../models/mercadopago.model';
import { MercadoPagoService } from '../../services/mercadopago.service';
import { ToastService } from '../../services/toast.service';
import { httpErrorMessage } from '../../utils/transaction-edit';

const PAGE_SIZE = 30;

@Component({
  selector: 'app-mercadopago',
  standalone: true,
  imports: [
    CommonModule,
    SidebarComponent,
    TopNavComponent,
    MercadoPagoDetailModalComponent,
  ],
  templateUrl: './mercadopago.component.html',
  styleUrl: './mercadopago.component.scss',
})
export class MercadoPagoComponent implements OnInit {
  private readonly mercadoPagoService = inject(MercadoPagoService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly rows = signal<MpPayment[]>([]);
  protected readonly listLoading = signal(false);
  protected readonly loadMoreLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly pagingTotal = signal<number | null>(null);
  protected readonly nextOffset = signal(0);

  protected readonly detailOpen = signal(false);
  protected readonly detailPayment = signal<MpPayment | null>(null);
  protected readonly detailLoading = signal(false);

  protected readonly hasMore = computed(() => {
    const total = this.pagingTotal();
    if (total == null) {
      return false;
    }
    return this.rows().length < total;
  });

  ngOnInit(): void {
    this.loadFirstPage();
  }

  protected reload(): void {
    this.loadFirstPage();
  }

  protected loadMore(): void {
    if (!this.hasMore()) {
      return;
    }
    this.fetchPage(true);
  }

  protected rowClickPayment(row: MpPayment): void {
    const rawId = row.id;
    if (rawId == null || `${rawId}`.trim() === '') {
      this.toast.error('This payment does not include an ID.');
      return;
    }

    const idStr = `${rawId}`.trim();

    this.detailOpen.set(true);
    this.detailPayment.set(null);
    this.detailLoading.set(true);

    this.mercadoPagoService
      .getPayment(idStr)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (payload) => {
          this.detailPayment.set(payload as MpPayment);
          this.detailLoading.set(false);
        },
        error: (err: unknown) => {
          this.detailLoading.set(false);
          this.detailOpen.set(false);
          this.detailPayment.set(null);
          this.toast.error(
            httpErrorMessage(err) ?? 'Could not load Mercado Pago payment.',
          );
        },
      });
  }

  protected closeDetail(): void {
    this.detailOpen.set(false);
    this.detailPayment.set(null);
    this.detailLoading.set(false);
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

  protected formatMoney(amount: unknown, currency?: string | null): string | null {
    if (typeof amount !== 'number' || Number.isNaN(amount)) {
      return null;
    }
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: String(currency ?? 'USD').substring(0, 3),
        minimumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${amount.toFixed(2)} ${currency ?? ''}`.trim();
    }
  }

  private loadFirstPage(): void {
    this.rows.set([]);
    this.nextOffset.set(0);
    this.pagingTotal.set(null);
    this.loadError.set(null);
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

    this.mercadoPagoService
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
          this.loadError.set(
            httpErrorMessage(err) ?? 'Could not load Mercado Pago payments.',
          );
        },
      });
  }
}
