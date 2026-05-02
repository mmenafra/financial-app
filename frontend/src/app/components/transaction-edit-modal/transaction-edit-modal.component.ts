import { CommonModule } from '@angular/common';
import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { CategorySelectComponent } from '../category-select/category-select.component';
import type {
  Category,
  Direction,
  Transaction,
  TransactionType,
  UpdateTransactionPayload,
} from '../../models/transaction.model';
import {
  positiveNumberValidator,
  round2,
  transactionEligibleToHideFromReports,
} from '../../utils/transaction-edit';

@Component({
  selector: 'app-transaction-edit-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, CategorySelectComponent],
  templateUrl: './transaction-edit-modal.component.html',
  styleUrl: './transaction-edit-modal.component.scss',
})
export class TransactionEditModalComponent {
  private readonly fb = inject(FormBuilder);

  readonly transaction = input<Transaction | null>(null);
  readonly categories = input.required<Category[]>();
  /** True while PATCH is in flight (from NgRx transactions page effects). */
  readonly isSaving = input(false);
  /** Server-side error message from failed update. */
  readonly serverError = input<string | null>(null);
  /** Prefix for form control ids (avoid duplicates when multiple instances exist). */
  readonly idPrefix = input('tx');
  /** When false, omit “Hide from totals / other screens”; used on Visa statement pages. */
  readonly hideToggleOffered = input(true);

  readonly saveRequested = output<{ id: string; payload: UpdateTransactionPayload }>();
  readonly dismissed = output<void>();

  private patchedForId: string | null = null;

  protected readonly editError = signal<string | null>(null);

  protected readonly displayError = computed(() => this.editError() ?? this.serverError());

  protected readonly titleId = computed(() => `${this.idPrefix()}-tx-edit-title`);
  protected readonly fieldId = (suffix: string) => `${this.idPrefix()}-edit-${suffix}`;

  protected readonly showHideControl = computed(() => {
    const t = this.transaction();
    return Boolean(this.hideToggleOffered() && t && transactionEligibleToHideFromReports(t));
  });

  protected readonly editTxForm = this.fb.group({
    description: ['', [Validators.required, Validators.maxLength(255)]],
    amount: ['', [Validators.required, positiveNumberValidator]],
    currency: ['CLP', [Validators.required]],
    direction: ['EXPENSE', [Validators.required]],
    category: [null as string | null],
    date: [''],
    hideFromReports: [false],
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
          hideFromReports: t.is_hidden ?? false,
        });
      }
      if (!t) {
        this.patchedForId = null;
      }
    });
  }

  protected closeModal(): void {
    if (this.isSaving()) {
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
    if (this.showHideControl()) {
      payload.is_hidden = Boolean(v.hideFromReports);
    }
    this.editError.set(null);
    this.saveRequested.emit({ id: tx.id, payload });
  }
}
