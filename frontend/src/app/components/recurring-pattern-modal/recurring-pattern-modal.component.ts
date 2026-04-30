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
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';

import type { RecurringFrequency, Transaction } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';
import { httpErrorMessage, positiveNumberValidator } from '../../utils/transaction-edit';

const FREQUENCIES: { value: RecurringFrequency; label: string }[] = [
  { value: 'DAILY', label: 'Daily' },
  { value: 'WEEKLY', label: 'Weekly' },
  { value: 'MONTHLY', label: 'Monthly' },
  { value: 'YEARLY', label: 'Yearly' },
];

function defaultPatternFromTransaction(tx: Transaction): string {
  const ext = tx.external_name?.trim();
  if (ext) {
    return ext;
  }
  return (tx.description ?? '').trim();
}

@Component({
  selector: 'app-recurring-pattern-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './recurring-pattern-modal.component.html',
  styleUrl: './recurring-pattern-modal.component.scss',
})
export class RecurringPatternModalComponent {
  private readonly fb = inject(FormBuilder);
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  readonly transaction = input<Transaction | null>(null);
  readonly idPrefix = input('tx');

  readonly created = output<void>();
  readonly dismissed = output<void>();

  private patchedForId: string | null = null;

  protected readonly submitting = signal(false);
  protected readonly submitError = signal<string | null>(null);

  protected readonly titleId = computed(() => `${this.idPrefix()}-recurring-title`);
  protected readonly fieldId = (suffix: string) => `${this.idPrefix()}-recurring-${suffix}`;

  protected readonly frequencyOptions = FREQUENCIES;

  protected readonly form = this.fb.group({
    description_pattern: ['', [Validators.required, Validators.maxLength(255)]],
    expected_amount: ['', [positiveNumberValidator]],
    frequency: ['MONTHLY' as RecurringFrequency, [Validators.required]],
  });

  constructor() {
    effect(() => {
      const t = this.transaction();
      if (t && t.id !== this.patchedForId) {
        this.patchedForId = t.id;
        this.submitError.set(null);
        this.form.reset({
          description_pattern: defaultPatternFromTransaction(t),
          expected_amount: t.amount ?? '',
          frequency: 'MONTHLY',
        });
      }
      if (!t) {
        this.patchedForId = null;
      }
    });
  }

  protected close(): void {
    if (this.submitting()) {
      return;
    }
    this.dismissed.emit();
  }

  protected onBackdrop(): void {
    this.close();
  }

  protected submit(): void {
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      return;
    }
    const tx = this.transaction();
    if (!tx) {
      return;
    }
    const v = this.form.value;
    const amtRaw = String(v.expected_amount ?? '').trim();
    const payload = {
      description_pattern: String(v.description_pattern ?? '').trim(),
      frequency: v.frequency as RecurringFrequency,
      ...(amtRaw ? { expected_amount: amtRaw } : { expected_amount: null }),
    };
    this.submitting.set(true);
    this.submitError.set(null);
    this.transactionService
      .createRecurringPattern(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.created.emit();
        },
        error: (err: unknown) => {
          this.submitting.set(false);
          this.submitError.set(httpErrorMessage(err) ?? 'Could not create recurring pattern.');
        },
      });
  }
}
