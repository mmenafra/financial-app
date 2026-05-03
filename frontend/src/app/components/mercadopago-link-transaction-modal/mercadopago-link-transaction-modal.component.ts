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

import type { Transaction } from '../../models/transaction.model';
import { MercadoPagoService } from '../../services/mercadopago.service';
import { TransactionService } from '../../services/transaction.service';
import { ToastService } from '../../services/toast.service';
import { httpErrorMessage } from '../../utils/transaction-edit';

@Component({
  selector: 'app-mercadopago-link-transaction-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './mercadopago-link-transaction-modal.component.html',
  styleUrl: './mercadopago-link-transaction-modal.component.scss',
})
export class MercadoPagoLinkTransactionModalComponent {
  private readonly transactionService = inject(TransactionService);
  private readonly mpService = inject(MercadoPagoService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  readonly mpPaymentId = input.required<string | number>();
  readonly dismissed = output<void>();

  protected readonly listLoading = signal(false);
  protected readonly listError = signal<string | null>(null);
  protected readonly candidates = signal<Transaction[]>([]);
  protected readonly searchQuery = signal('');
  protected readonly linkingId = signal<string | null>(null);

  protected readonly titleId = 'mp-link-tx-title';

  protected readonly filteredRows = computed(() => {
    const q = this.searchQuery().trim().toLowerCase();
    const rows = this.candidates();
    if (!q) {
      return rows;
    }
    return rows.filter((t) => {
      const desc = (t.description ?? '').toLowerCase();
      const ext = (t.external_name ?? '').toLowerCase();
      const dateStr = (t.transaction_date ?? '').toString().toLowerCase();
      const amountStr = String(t.amount ?? '').toLowerCase();
      return desc.includes(q) || ext.includes(q) || dateStr.includes(q) || amountStr.includes(q);
    });
  });

  constructor() {
    effect(() => {
      this.mpPaymentId();
      untracked(() => {
        this.searchQuery.set('');
        this.candidates.set([]);
        this.listError.set(null);
        this.loadCandidates();
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

  protected formatClp(amount: string | number): string {
    const n = typeof amount === 'string' ? Number(amount) : amount;
    if (Number.isNaN(n)) {
      return String(amount);
    }
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency: 'CLP',
      currencyDisplay: 'narrowSymbol',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(n);
  }

  protected linkRow(tx: Transaction, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    if (this.linkingId() != null) {
      return;
    }
    this.linkingId.set(tx.id);
    this.mpService
      .linkToVisaTransaction(this.mpPaymentId(), tx.id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.linkingId.set(null)),
      )
      .subscribe({
        next: () => {
          this.toast.success('Transaction linked');
          this.dismissed.emit();
        },
        error: (err: unknown) => {
          this.toast.error(httpErrorMessage(err) ?? 'Could not create link.');
        },
      });
  }

  private loadCandidates(): void {
    this.listLoading.set(true);
    this.transactionService
      .getAllTransactions({
        source: 'CREDIT_CARD_NATIONAL',
        includeHidden: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => {
          const sorted = [...rows].sort((a, b) => {
            const da = (a.transaction_date ?? '').toString();
            const db = (b.transaction_date ?? '').toString();
            return db.localeCompare(da);
          });
          this.candidates.set(sorted);
          this.listLoading.set(false);
        },
        error: (err: unknown) => {
          this.listLoading.set(false);
          this.listError.set(httpErrorMessage(err) ?? 'Could not load transactions.');
        },
      });
  }
}
