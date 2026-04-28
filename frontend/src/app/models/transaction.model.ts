/** Mirrors `TransactionSerializer` / `Transaction` model. */
export interface Transaction {
  id: string;
  created_at: string;
  updated_at: string;
  user: number | null;
  description: string;
  amount: string;
  currency: string;
  amount_local: string | null;
  exchange_rate: string | null;
  transaction_type: TransactionType;
  direction: Direction;
  category: string | null;
  subcategory: string | null;
  source: Source;
  original_reference: string | null;
  external_id: string | null;
  external_name: string | null;
  is_installment: boolean;
  installment_current: number | null;
  installment_total: number | null;
  installment_amount: string | null;
  installment_group_id: string | null;
  raw_data: Record<string, unknown> | null;
  imported_at: string | null;
  status: TransactionStatus;
  /** Set when this row is a split line; the bundle is not listed. */
  parent: string | null;
  /** IDs of child split lines; empty unless this is a bundle (bundles are hidden from list). */
  splits: string[];
}

export type TransactionType = 'DEBIT' | 'CREDIT' | 'TRANSFER';

export type Direction = 'INCOME' | 'EXPENSE';

export type Source =
  | 'MERCADOPAGO'
  | 'BANK_ACCOUNT'
  | 'CREDIT_CARD_NATIONAL'
  | 'CREDIT_CARD_INTERNATIONAL';

export type TransactionStatus = 'PENDING' | 'CONFIRMED' | 'CANCELLED';

/** Mirrors `CategorySerializer`. */
export interface Category {
  id: string;
  created_at: string;
  updated_at: string;
  user: number | null;
  name: string;
  parent: string | null;
  icon: string | null;
  color: string | null;
}

/** DRF `PageNumberPagination` envelope for transactions list. */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
  /** Sum of EXPENSE amounts for the filtered period (injected by the list endpoint). */
  total_spent?: string;
  /** Sum of EXPENSE amounts for the previous calendar month. */
  prev_month_spent?: string;
}

export interface TransactionFilters {
  year?: number;
  month?: number;
  category?: string;
  source?: Source;
  page?: number;
  pageSize?: number;
}

/** Body for POST /api/transactions/:id/split/ */
export interface SplitItem {
  description: string;
  amount: string;
  category: string | null;
}

/** POST /api/transactions/import-bank-statement/ (Banco Santander .dat) */
export interface BankStatementImportRowError {
  row: Record<string, unknown>;
  error: string;
}

export interface BankStatementImportResult {
  created: number;
  skipped: number;
  failed: number;
  transactions: Transaction[];
  errors: BankStatementImportRowError[];
  /** Gemini bulk categorization was invoked (needs API key + categories + uncategorized rows). */
  ai_categorization_attempted?: boolean;
  ai_categorization_failed?: boolean;
  ai_failure_detail?: string | null;
}

/** Body for POST /api/transactions/ */
export interface CreateTransactionPayload {
  description: string;
  amount: string;
  currency: string;
  direction: Direction;
  transaction_type: TransactionType;
  source: Source;
  category?: string | null;
  created_at?: string;
}

/** Body for PATCH /api/transactions/:id/ */
export interface UpdateTransactionPayload {
  description?: string;
  amount?: string;
  currency?: string;
  direction?: Direction;
  transaction_type?: TransactionType;
  category?: string | null;
  created_at?: string;
}
