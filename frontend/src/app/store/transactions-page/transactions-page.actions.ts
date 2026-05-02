import { createActionGroup, emptyProps, props } from '@ngrx/store';

import type {
  Category,
  CreateTransactionPayload,
  Source,
  SplitItem,
  Transaction,
  UpdateTransactionPayload,
} from '../../models/transaction.model';

export const TransactionsPageActions = createActionGroup({
  source: 'Transactions Page',
  events: {
    initialized: props<{ year: number; month: number }>(),
    yearChanged: props<{ year: number }>(),
    monthChanged: props<{ month: number }>(),
    filtersCommitted: props<{ filterCategoryId?: string; filterSource?: Source }>(),
    filtersCleared: emptyProps(),
    filterChipRemoved: props<{ kind: 'category' | 'source' }>(),
    pageChanged: props<{ page: number }>(),
    listRefreshRequested: emptyProps(),
    /** Re-fetch aggregates (and totalCount) without replacing the transaction rows. */
    summaryRefreshRequested: emptyProps(),
    importCompleted: emptyProps(),
    loadStarted: emptyProps(),
    loadSucceeded: props<{
      transactions: Transaction[];
      totalCount: number;
      totalsByCurrency?: Record<string, string>;
      prevTotalsByCurrency?: Record<string, string>;
      totalSpent?: string;
      categories?: Category[];
    }>(),
    summaryLoadSucceeded: props<{
      totalCount: number;
      totalsByCurrency?: Record<string, string>;
      prevTotalsByCurrency?: Record<string, string>;
      totalSpent?: string;
    }>(),
    loadFailed: props<{ message: string }>(),
    deleteRequested: props<{ id: string }>(),
    updateRequested: props<{ id: string; payload: UpdateTransactionPayload }>(),
    createRequested: props<{ payload: CreateTransactionPayload }>(),
    splitRequested: props<{ id: string; items: SplitItem[] }>(),
    deleteMutationSucceeded: props<{ id: string }>(),
    deleteMutationFailed: props<{ message: string }>(),
    updateMutationSucceeded: props<{ transaction: Transaction }>(),
    updateMutationFailed: props<{ message: string }>(),
    createMutationSucceeded: emptyProps(),
    createMutationFailed: props<{ message: string }>(),
    splitMutationSucceeded: props<{ parentId: string; transactions: Transaction[] }>(),
    splitMutationFailed: props<{ message: string }>(),
  },
});
