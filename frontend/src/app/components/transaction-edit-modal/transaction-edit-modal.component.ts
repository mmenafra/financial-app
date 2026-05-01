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
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { CategorySelectComponent } from '../category-select/category-select.component';
import type {
  Category,
  Direction,
  Transaction,
  TransactionType,
  UpdateTransactionPayload,
} from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';
import { httpErrorMessage, positiveNumberValidator, round2 } from '../../utils/transaction-edit';

@Component({
  selector: 'app-transaction-edit-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, CategorySelectComponent],
  templateUrl: './transaction-edit-modal.component.html',
  styleUrl: './transaction-edit-modal.component.scss',
})
export class TransactionEditModalComponent {
  private readonly fb = inject(FormBuilder);
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  readonly transaction = input<Transaction | null>(null);
  readonly categories = input.required<Category[]>();
  /** Prefix for form control ids (avoid duplicates when multiple instances exist). */
  readonly idPrefix = input('tx');

  readonly saved = output<void>();
  readonly dismissed = output<void>();

  private patchedForId: string | null = null;

  protected readonly editSubmitting = signal(false);
  protected readonly editError = signal<string | null>(null);

  protected readonly titleId = computed(() => `${this.idPrefix()}-tx-edit-title`);
  protected readonly fieldId = (suffix: string) => `${this.idPrefix()}-edit-${suffix}`;

  protected readonly editTxForm = this.fb.group({
    description: ['', [Validators.required, Validators.maxLength(255)]],
    amount: ['', [Validators.required, positiveNumberValidator]],
    currency: ['CLP', [Validators.required]],
    direction: ['EXPENSE', [Validators.required]],
    category: [null as string | null],
    date: [''],
  });

  constructor() {
    effect(() => {
      const t = this.transaction();
      if (t && t.id !== this.patchedForId) {
        this.patchedForId = t.id;
        this.editError.set(null);
        this.editTxForm.reset({
          description: t.description,
          amount: t.amount,
          currency: t.currency,
          direction: t.direction,
          category: t.category ?? null,
          date: t.transaction_date ?? t.created_at.slice(0, 10),
        });
      }
      if (!t) {
        this.patchedForId = null;
      }
    });
  }

  protected closeModal(): void {
    if (this.editSubmitting()) {
      return;
    }
    this.dismissed.emit();
  }

  protected onBackdrop(): void {
    this.closeModal();
  }

  protected submitEditTx(): void {
    this.editTxForm.markAllAsTouched();
    if (this.editTxForm.invalid) {
      return;
    }
    const tx = this.transaction();
    if (!tx) {
      return;
    }
    const v = this.editTxForm.value;
    const direction = (v.direction ?? 'EXPENSE') as Direction;
    const txType: TransactionType = direction === 'INCOME' ? 'CREDIT' : 'DEBIT';
    const dateVal = v.date?.trim() || undefined;
    const payload: UpdateTransactionPayload = {
      description: String(v.description ?? '').trim(),
      amount: round2(Number(v.amount)).toFixed(2),
      currency: String(v.currency ?? 'CLP'),
      direction,
      transaction_type: txType,
      category: v.category ?? null,
      ...(dateVal ? { transaction_date: dateVal } : {}),
    };
    this.editSubmitting.set(true);
    this.editError.set(null);
    this.transactionService
      .updateTransaction(tx.id, payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.editSubmitting.set(false);
          this.saved.emit();
        },
        error: (err: unknown) => {
          this.editSubmitting.set(false);
          this.editError.set(httpErrorMessage(err) ?? 'Could not update transaction.');
        },
      });
  }
}
