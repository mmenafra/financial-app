import type { Transaction } from '../../models/transaction.model';
import type { TransactionsPageState } from './transactions-page.state';

/** Whether a transaction belongs in the list for the current year/month and committed filters. */
export function transactionInView(t: Transaction, state: TransactionsPageState): boolean {
  const iso = t.transaction_date ?? t.created_at.slice(0, 10);
  const parts = iso.slice(0, 10).split('-').map(Number);
  const y = parts[0];
  const m = parts[1];
  if (y !== state.year || m !== state.month) {
    return false;
  }
  if (state.filterCategoryId != null && t.category !== state.filterCategoryId) {
    return false;
  }
  if (state.filterSource != null && t.source !== state.filterSource) {
    return false;
  }
  if (!state.showHiddenTransactions && t.is_hidden) {
    return false;
  }
  return true;
}
