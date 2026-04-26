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
  is_installment: boolean;
  installment_current: number | null;
  installment_total: number | null;
  installment_amount: string | null;
  installment_group_id: string | null;
  raw_data: Record<string, unknown> | null;
  imported_at: string | null;
  status: TransactionStatus;
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
}

export interface TransactionFilters {
  year?: number;
  month?: number;
  category?: string;
  source?: Source;
  page?: number;
  pageSize?: number;
}
