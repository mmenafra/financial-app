import { createFeature, createReducer, on } from '@ngrx/store';

import type { Transaction } from '../../models/transaction.model';
import { TransactionsPageActions } from './transactions-page.actions';
import { transactionInView } from './transactions-page.helpers';
import { transactionsPageInitialState } from './transactions-page.state';

export const transactionsPageFeature = createFeature({
  name: 'transactionsPage',
  reducer: createReducer(
    transactionsPageInitialState,
    on(TransactionsPageActions.initialized, (state, { year, month }) => ({
      ...state,
      year,
      month,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.yearChanged, (state, { year }) => ({
      ...state,
      year,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.monthChanged, (state, { month }) => ({
      ...state,
      month,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.filtersCommitted, (state, { filterCategoryId, filterSource }) => ({
      ...state,
      filterCategoryId,
      filterSource,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.filtersCleared, (state) => ({
      ...state,
      filterCategoryId: undefined,
      filterSource: undefined,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.filterChipRemoved, (state, { kind }) => ({
      ...state,
      filterCategoryId: kind === 'category' ? undefined : state.filterCategoryId,
      filterSource: kind === 'source' ? undefined : state.filterSource,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.showHiddenTransactionsToggled, (state) => ({
      ...state,
      showHiddenTransactions: !state.showHiddenTransactions,
      page: 1,
      loadError: null,
    })),
    on(TransactionsPageActions.pageChanged, (state, { page }) => ({
      ...state,
      page,
      loadError: null,
    })),
    on(TransactionsPageActions.loadStarted, (state) => ({
      ...state,
      loading: true,
      loadError: null,
    })),
    on(
      TransactionsPageActions.loadSucceeded,
      (
        state,
        {
          transactions,
          totalCount,
          totalsByCurrency,
          prevTotalsByCurrency,
          totalSpent,
          categories,
        },
      ) => ({
        ...state,
        loading: false,
        loadError: null,
        transactions,
        totalCount,
        totalsByCurrency,
        prevTotalsByCurrency,
        totalSpent,
        ...(categories != null ? { categories, categoriesLoaded: true } : {}),
      }),
    ),
    on(
      TransactionsPageActions.summaryLoadSucceeded,
      (state, { totalCount, totalsByCurrency, prevTotalsByCurrency, totalSpent }) => ({
        ...state,
        totalCount,
        totalsByCurrency: totalsByCurrency ?? state.totalsByCurrency,
        prevTotalsByCurrency: prevTotalsByCurrency ?? state.prevTotalsByCurrency,
        totalSpent: totalSpent ?? state.totalSpent,
      }),
    ),
    on(TransactionsPageActions.loadFailed, (state, { message }) => ({
      ...state,
      loading: false,
      loadError: message,
    })),
    on(TransactionsPageActions.deleteMutationSucceeded, (state, { id }) => {
      const nextTxs = state.transactions.filter((x) => x.id !== id);
      const nextCount = Math.max(0, state.totalCount - 1);
      let page = state.page;
      if (nextTxs.length === 0 && page > 1) {
        page = page - 1;
      }
      return {
        ...state,
        transactions: nextTxs,
        totalCount: nextCount,
        page,
      };
    }),
    on(
      TransactionsPageActions.splitMutationSucceeded,
      (state, { parentId, transactions: newRows }) => {
        const idx = state.transactions.findIndex((x) => x.id === parentId);
        if (idx === -1) {
          return state;
        }
        const transactions: Transaction[] = [
          ...state.transactions.slice(0, idx),
          ...newRows,
          ...state.transactions.slice(idx + 1),
        ];
        const delta = newRows.length - 1;
        return {
          ...state,
          transactions,
          totalCount: Math.max(0, state.totalCount + delta),
        };
      },
    ),
    on(TransactionsPageActions.updateRequested, (state) => ({
      ...state,
      isUpdatingTransaction: true,
      updateError: null,
    })),
    on(TransactionsPageActions.updateMutationSucceeded, (state, { transaction }) => {
      const inView = transactionInView(transaction, state);
      let transactions: Transaction[];
      let totalCount = state.totalCount;
      if (inView) {
        transactions = state.transactions.map((x) => (x.id === transaction.id ? transaction : x));
      } else {
        const had = state.transactions.some((x) => x.id === transaction.id);
        transactions = state.transactions.filter((x) => x.id !== transaction.id);
        if (had) {
          totalCount = Math.max(0, totalCount - 1);
        }
      }
      return {
        ...state,
        transactions,
        totalCount,
        isUpdatingTransaction: false,
        updateError: null,
      };
    }),
    on(TransactionsPageActions.updateMutationFailed, (state, { message }) => ({
      ...state,
      isUpdatingTransaction: false,
      updateError: message,
    })),
  ),
});
