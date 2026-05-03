import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormControl, ReactiveFormsModule } from '@angular/forms';
import { forkJoin, type Observable } from 'rxjs';

import { CategorySelectComponent } from '../category-select/category-select.component';
import type {
  BankStatementImportResult,
  BankStatementImportSkippedItem,
  Category,
  Transaction,
} from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';
import { normalizeBankStatementImportResult } from '../../utils/normalize-bank-statement-import-result';

@Component({
  selector: 'app-import-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, CategorySelectComponent],
  templateUrl: './import-modal.component.html',
  styleUrl: './import-modal.component.scss',
})
export class ImportModalComponent implements OnChanges {
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly transactionService = inject(TransactionService);

  /** multipart POST that returns BankStatementImportResult; omit when only `initialImportResult` is used */
  @Input() submitImportFn?: (file: File) => Observable<BankStatementImportResult>;

  /** When set (e.g. from re-run API), skip file upload and show the same summary/review flow as after a successful POST */
  @Input() initialImportResult: BankStatementImportResult | null = null;

  /** e.g. `.dat`, `.pdf` */
  @Input({ required: true }) accept!: string;

  @Input({ required: true }) modalTitle!: string;

  @Input({ required: true }) modalDescription!: string;

  @Input() categories: Category[] = [];

  @Input() chooseFilePrompt = 'Choose a file first.';

  @Output() readonly closed = new EventEmitter<void>();
  /** After successful import POST and after finish review (reload in parent) */
  @Output() readonly imported = new EventEmitter<void>();
  /** When the user completes the review step and the modal closes (not on upload-only success). */
  @Output() readonly importReviewCompleted = new EventEmitter<void>();

  protected readonly importFile = signal<File | null>(null);
  protected readonly importSubmitting = signal(false);
  protected readonly importResult = signal<BankStatementImportResult | null>(null);
  protected readonly importError = signal<string | null>(null);
  protected readonly importReviewStep = signal(false);
  /** Visa Nacional: show Mercado Pago link summary before category review. */
  protected readonly importMercadoPagoStep = signal(false);
  protected importReviewControls: FormControl<string | null>[] = [];
  protected readonly importFinishing = signal(false);
  protected readonly importFinishError = signal<string | null>(null);

  ngOnChanges(changes: SimpleChanges): void {
    const initCh = changes['initialImportResult'];
    if (!initCh?.currentValue || this.submitImportFn) {
      return;
    }
    this.applyInitialImportResult(initCh.currentValue as BankStatementImportResult);
  }

  private applyInitialImportResult(res: BankStatementImportResult): void {
    if (!res) {
      return;
    }
    this.importFile.set(null);
    this.importResult.set(normalizeBankStatementImportResult(res));
    this.importReviewStep.set(false);
    this.importMercadoPagoStep.set(false);
    this.importReviewControls = [];
    this.importFinishError.set(null);
    this.importError.set(null);
    this.importSubmitting.set(false);
    this.imported.emit();
  }

  close(): void {
    if (this.importSubmitting() || this.importFinishing()) {
      return;
    }
    this.closed.emit();
    this.importFile.set(null);
    this.importResult.set(null);
    this.importError.set(null);
    this.importReviewStep.set(false);
    this.importMercadoPagoStep.set(false);
    this.importReviewControls = [];
    this.importFinishing.set(false);
    this.importFinishError.set(null);
  }

  protected onImportFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0];
    this.importFile.set(f ?? null);
    this.importError.set(null);
  }

  protected submitImport(): void {
    const submit = this.submitImportFn;
    if (!submit) {
      return;
    }
    const file = this.importFile();
    if (!file) {
      this.importError.set(this.chooseFilePrompt);
      return;
    }
    this.importSubmitting.set(true);
    this.importError.set(null);
    submit(file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.importSubmitting.set(false);
          this.importResult.set(normalizeBankStatementImportResult(res));
          this.importReviewStep.set(false);
          this.importMercadoPagoStep.set(false);
          this.importReviewControls = [];
          this.importFinishError.set(null);
          this.imported.emit();
        },
        error: (err: unknown) => {
          this.importSubmitting.set(false);
          this.importError.set(
            this.httpErrorMessage(err) ?? 'Import failed. Check the file and try again.',
          );
        },
      });
  }

  protected goToReviewStep(): void {
    const res = this.importResult();
    if (!res) {
      return;
    }
    this.importMercadoPagoStep.set(false);
    this.importReviewControls = res.transactions.map((tx) =>
      this.fb.control<string | null>(tx.category ?? null),
    );
    this.importReviewStep.set(true);
    this.importFinishError.set(null);
  }

  protected onSummaryNextFromImport(): void {
    const res = this.importResult();
    if (!res) {
      return;
    }
    if (this.hasMercadoPagoImportMeta(res)) {
      this.importMercadoPagoStep.set(true);
    } else {
      this.goToReviewStep();
    }
  }

  protected continueFromMercadoPagoToCategories(): void {
    this.importMercadoPagoStep.set(false);
    this.goToReviewStep();
  }

  private hasMercadoPagoImportMeta(res: BankStatementImportResult): boolean {
    return res.mercadopago_payments_synced !== undefined;
  }

  protected finishImportReview(): void {
    const res = this.importResult();
    if (!res || this.importFinishing()) {
      return;
    }
    const txs = res.transactions;
    const patches: Observable<Transaction>[] = [];
    for (let i = 0; i < txs.length; i++) {
      const tx = txs[i];
      const ctrl = this.importReviewControls[i];
      if (!ctrl) {
        continue;
      }
      const nextCat = ctrl.value ?? null;
      const prevCat = tx.category ?? null;
      if (nextCat === prevCat) {
        continue;
      }
      patches.push(this.transactionService.updateTransaction(tx.id, { category: nextCat }));
    }
    if (patches.length === 0) {
      this.importFile.set(null);
      this.importResult.set(null);
      this.importError.set(null);
      this.importReviewStep.set(false);
      this.importMercadoPagoStep.set(false);
      this.importReviewControls = [];
      this.importFinishError.set(null);
      this.importReviewCompleted.emit();
      this.imported.emit();
      this.closed.emit();
      return;
    }
    this.importFinishing.set(true);
    this.importFinishError.set(null);
    forkJoin(patches)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.importFinishing.set(false);
          this.importFile.set(null);
          this.importResult.set(null);
          this.importError.set(null);
          this.importReviewStep.set(false);
          this.importMercadoPagoStep.set(false);
          this.importReviewControls = [];
          this.importFinishError.set(null);
          this.importReviewCompleted.emit();
          this.imported.emit();
          this.closed.emit();
        },
        error: (err: unknown) => {
          this.importFinishing.set(false);
          this.importFinishError.set(
            this.httpErrorMessage(err) ?? 'Could not update categories. Try again.',
          );
        },
      });
  }

  protected importErrorRowPreview(row: Record<string, unknown>): string {
    const d = row['date'];
    const desc = row['description'];
    const parts: string[] = [];
    if (typeof d === 'string') {
      parts.push(d);
    }
    if (typeof desc === 'string') {
      parts.push(desc);
    }
    if (parts.length) {
      return parts.join(' — ');
    }
    try {
      return JSON.stringify(row);
    } catch {
      return String(row);
    }
  }

  protected displayAmount(t: Transaction | BankStatementImportSkippedItem): string {
    const formatted = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: t.currency ?? 'USD',
      minimumFractionDigits: 2,
    }).format(Number(t.amount));
    if (t.direction === 'INCOME') {
      return `+${formatted}`;
    }
    return `-${formatted}`;
  }

  protected amountClass(t: Transaction | BankStatementImportSkippedItem): string {
    return t.direction === 'INCOME' ? 'amount-income' : 'amount-expense';
  }

  private httpErrorMessage(err: unknown): string | null {
    if (err && typeof err === 'object' && 'error' in err) {
      const e = (err as { error?: unknown }).error;
      if (typeof e === 'string' && e) {
        return e;
      }
      if (e && typeof e === 'object' && 'detail' in e) {
        const d = (e as { detail?: unknown }).detail;
        if (typeof d === 'string') {
          return d;
        }
      }
      if (e && typeof e === 'object' && 'items' in e) {
        const it = (e as { items?: unknown }).items;
        if (typeof it === 'string') {
          return it;
        }
        if (Array.isArray(it) && it.length > 0 && typeof it[0] === 'string') {
          return it[0] as string;
        }
      }
    }
    return null;
  }
}
