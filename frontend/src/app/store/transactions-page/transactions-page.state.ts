import type { Category, Source, Transaction } from '../../models/transaction.model';

export const TRANSACTIONS_PAGE_SIZE = 100;

/** Public for helpers that validate rows against active filters. */
export interface TransactionsPageState {
  year: number;
  month: number;
  page: number;
  filterCategoryId: string | undefined;
  filterSource: Source | undefined;
  /** When true, GET /transactions/ includes rows hidden from other screens (default false). */
  showHiddenTransactions: boolean;
  categories: Category[];
  categoriesLoaded: boolean;
  transactions: Transaction[];
  totalCount: number;
  totalsByCurrency: Record<string, string> | undefined;
  prevTotalsByCurrency: Record<string, string> | undefined;
  totalSpent: string | undefined;
  loading: boolean;
  loadError: string | null;
  isUpdatingTransaction: boolean;
  updateError: string | null;
}

export const transactionsPageInitialState: TransactionsPageState = {
  year: new Date().getFullYear(),
  month: new Date().getMonth() + 1,
  page: 1,
  filterCategoryId: undefined,
  filterSource: undefined,
  showHiddenTransactions: false,
  categories: [],
  categoriesLoaded: false,
  transactions: [],
  totalCount: 0,
  totalsByCurrency: undefined,
  prevTotalsByCurrency: undefined,
  totalSpent: undefined,
  loading: false,
  loadError: null,
  isUpdatingTransaction: false,
  updateError: null,
};
