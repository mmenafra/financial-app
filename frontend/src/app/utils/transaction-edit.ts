import type { AbstractControl, ValidationErrors } from '@angular/forms';

import type { Transaction } from '../models/transaction.model';

/** Amount > 0 when non-empty (pair with Validators.required). */
export function positiveNumberValidator(control: AbstractControl): ValidationErrors | null {
  const raw = String(control.value ?? '').trim();
  if (!raw) {
    return null;
  }
  const n = Number(raw);
  if (Number.isNaN(n) || n <= 0) {
    return { positiveNumber: true };
  }
  return null;
}

export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** National / international Visa card rows cannot use “hide from reports”. */
export function transactionEligibleToHideFromReports(tx: Pick<Transaction, 'source'>): boolean {
  return tx.source !== 'CREDIT_CARD_NATIONAL' && tx.source !== 'CREDIT_CARD_INTERNATIONAL';
}

/** Best-effort message from Angular HttpClient / DRF error bodies. */
export function httpErrorMessage(err: unknown): string | null {
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
