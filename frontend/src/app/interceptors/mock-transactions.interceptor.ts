import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { of } from 'rxjs';

import type {
  Category,
  Direction,
  Source,
  Transaction,
  TransactionStatus,
  TransactionType,
} from '../models/transaction.model';

/** Set to `false` to pass requests through to the real API. */
export const MOCK_ENABLED = true;

const CAT_TECH = 'a1000000-0000-4000-8000-000000000001';
const CAT_DINING = 'a1000000-0000-4000-8000-000000000002';
const CAT_INCOME = 'a1000000-0000-4000-8000-000000000003';
const CAT_TRANSPORT = 'a1000000-0000-4000-8000-000000000004';
const CAT_HEALTH = 'a1000000-0000-4000-8000-000000000005';

const MOCK_CATEGORIES: Category[] = [
  {
    id: CAT_TECH,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    user: 1,
    name: 'Technology',
    parent: null,
    icon: 'shopping_bag',
    color: '#2563eb',
  },
  {
    id: CAT_DINING,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    user: 1,
    name: 'Dining Out',
    parent: null,
    icon: 'restaurant',
    color: '#7dd3fc',
  },
  {
    id: CAT_INCOME,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    user: 1,
    name: 'Income',
    parent: null,
    icon: 'add_circle',
    color: '#22c55e',
  },
  {
    id: CAT_TRANSPORT,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    user: 1,
    name: 'Transport',
    parent: null,
    icon: 'directions_car',
    color: '#38bdf8',
  },
  {
    id: CAT_HEALTH,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    user: 1,
    name: 'Health',
    parent: null,
    icon: 'fitness_center',
    color: '#0ea5e9',
  },
];

function tx(
  idSuffix: string,
  createdAt: string,
  partial: Pick<
    Transaction,
    | 'description'
    | 'amount'
    | 'currency'
    | 'transaction_type'
    | 'direction'
    | 'category'
    | 'source'
  > &
    Partial<Transaction>,
): Transaction {
  const id = `b2000000-0000-4000-8000-${idSuffix}`;
  return {
    id,
    created_at: createdAt,
    updated_at: createdAt,
    user: 1,
    description: partial.description,
    amount: partial.amount,
    currency: partial.currency,
    amount_local: partial.amount_local ?? null,
    exchange_rate: partial.exchange_rate ?? null,
    transaction_type: partial.transaction_type,
    direction: partial.direction,
    category: partial.category ?? null,
    subcategory: partial.subcategory ?? null,
    source: partial.source,
    original_reference: partial.original_reference ?? null,
    external_id: partial.external_id ?? `mock-${idSuffix}`,
    is_installment: partial.is_installment ?? false,
    installment_current: partial.installment_current ?? null,
    installment_total: partial.installment_total ?? null,
    installment_amount: partial.installment_amount ?? null,
    installment_group_id: partial.installment_group_id ?? null,
    raw_data: partial.raw_data ?? null,
    imported_at: partial.imported_at ?? createdAt,
    status: (partial.status as TransactionStatus | undefined) ?? 'CONFIRMED',
  };
}

/** Design-like rows + generated rows to reach 248 for Oct 2023. */
function buildAllMockTransactions(): Transaction[] {
  const seed: Transaction[] = [
    tx('000000000001', '2023-10-24T14:30:00Z', {
      description: 'Apple Store Infinite Loop',
      amount: '1299.00',
      currency: 'USD',
      transaction_type: 'DEBIT',
      direction: 'EXPENSE',
      category: CAT_TECH,
      source: 'CREDIT_CARD_INTERNATIONAL',
    }),
    tx('000000000002', '2023-10-23T19:00:00Z', {
      description: 'The Modern Bistro',
      amount: '84.50',
      currency: 'USD',
      transaction_type: 'DEBIT',
      direction: 'EXPENSE',
      category: CAT_DINING,
      source: 'BANK_ACCOUNT',
    }),
    tx('000000000003', '2023-10-21T09:00:00Z', {
      description: 'Monthly Salary Deposit',
      amount: '8500.00',
      currency: 'USD',
      transaction_type: 'CREDIT',
      direction: 'INCOME',
      category: CAT_INCOME,
      source: 'BANK_ACCOUNT',
    }),
    tx('000000000004', '2023-10-21T08:15:00Z', {
      description: 'Uber Technologies Inc.',
      amount: '32.15',
      currency: 'ARS',
      transaction_type: 'DEBIT',
      direction: 'EXPENSE',
      category: CAT_TRANSPORT,
      source: 'CREDIT_CARD_NATIONAL',
    }),
    tx('000000000005', '2023-10-18T11:20:00Z', {
      description: 'Equinox Luxury Fitness',
      amount: '215.00',
      currency: 'USD',
      transaction_type: 'DEBIT',
      direction: 'EXPENSE',
      category: CAT_HEALTH,
      source: 'CREDIT_CARD_INTERNATIONAL',
    }),
  ];

  const sources: Source[] = [
    'MERCADOPAGO',
    'BANK_ACCOUNT',
    'CREDIT_CARD_NATIONAL',
    'CREDIT_CARD_INTERNATIONAL',
  ];
  const categoryIds = [CAT_TECH, CAT_DINING, CAT_TRANSPORT, CAT_HEALTH];
  const types: TransactionType[] = ['DEBIT', 'CREDIT', 'DEBIT', 'DEBIT'];

  const extra: Transaction[] = [];
  let n = seed.length;
  for (let d = 31; d >= 1 && n < 248; d--) {
    for (let k = 0; k < 9 && n < 248; k++) {
      const direction: Direction = n % 12 === 0 ? 'INCOME' : 'EXPENSE';
      const amountNum =
        direction === 'INCOME'
          ? 2000 + (n % 50) * 100
          : 12.5 + (n % 97) * 3.17 + (k % 5) * 10;
      const amount = amountNum.toFixed(2);
      const createdAt = `2023-10-${String(d).padStart(2, '0')}T${String((10 + k) % 24).padStart(2, '0')}:15:00Z`;
      const suffix = String(n + 1).padStart(12, '0');
      extra.push(
        tx(suffix, createdAt, {
          description:
            direction === 'INCOME'
              ? `Transfer in #${n}`
              : `Card purchase ${n} — Merchant ${k}`,
          amount,
          currency: n % 7 === 0 ? 'ARS' : 'USD',
          transaction_type: types[n % types.length],
          direction,
          category: direction === 'INCOME' ? CAT_INCOME : categoryIds[n % categoryIds.length],
          source: sources[n % sources.length],
        }),
      );
      n++;
    }
  }

  const october = [...seed, ...extra];

  /** Prior month expenses for trend line when viewing October 2023. */
  const september: Transaction[] = [];
  let s = 0;
  for (let d = 28; d >= 1 && s < 180; d--) {
    for (let j = 0; j < 7 && s < 180; j++) {
      const amountNum = 18.25 + (s % 89) * 4.11 + j * 3;
      const suffix = `9${String(s + 1).padStart(11, '0')}`;
      september.push(
        tx(suffix, `2023-09-${String(d).padStart(2, '0')}T${String((8 + j) % 24).padStart(2, '0')}:20:00Z`, {
          description: `September spend ${s + 1}`,
          amount: amountNum.toFixed(2),
          currency: s % 6 === 0 ? 'ARS' : 'USD',
          transaction_type: 'DEBIT',
          direction: 'EXPENSE',
          category: categoryIds[s % categoryIds.length],
          source: sources[s % sources.length],
        }),
      );
      s++;
    }
  }

  const all = [...october, ...september];
  return all.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
}

const ALL_MOCK = buildAllMockTransactions();

function parsePathname(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    const base = url.split('?')[0];
    const idx = base.indexOf('/api/');
    return idx >= 0 ? base.slice(idx) : base;
  }
}

function isTransactionsListGet(url: string, method: string): boolean {
  if (method !== 'GET') {
    return false;
  }
  const path = parsePathname(url);
  return path === '/api/transactions' || path === '/api/transactions/';
}

function isCategoriesListGet(url: string, method: string): boolean {
  if (method !== 'GET') {
    return false;
  }
  const path = parsePathname(url);
  return path === '/api/categories' || path === '/api/categories/';
}

function readIntParam(url: string, key: string): number | undefined {
  try {
    const u = new URL(url.includes('http') ? url : `http://local.invalid${url}`);
    const raw = u.searchParams.get(key);
    if (raw == null || raw === '') {
      return undefined;
    }
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  } catch {
    return undefined;
  }
}

function filterByYearMonth(rows: Transaction[], year?: number, month?: number): Transaction[] {
  if (year == null && month == null) {
    return rows;
  }
  return rows.filter((r) => {
    const d = new Date(r.created_at);
    if (year != null && d.getUTCFullYear() !== year) {
      return false;
    }
    if (month != null && d.getUTCMonth() + 1 !== month) {
      return false;
    }
    return true;
  });
}

export const mockTransactionsInterceptor: HttpInterceptorFn = (req, next) => {
  if (!MOCK_ENABLED) {
    return next(req);
  }

  if (isCategoriesListGet(req.url, req.method)) {
    return of(new HttpResponse({ status: 200, body: MOCK_CATEGORIES }));
  }

  if (!isTransactionsListGet(req.url, req.method)) {
    return next(req);
  }

  const year = readIntParam(req.url, 'year');
  const month = readIntParam(req.url, 'month');
  const page = readIntParam(req.url, 'page') ?? 1;
  const pageSize = readIntParam(req.url, 'page_size') ?? 20;

  let filtered = filterByYearMonth(ALL_MOCK, year, month);

  const categoryFilter = readStringParam(req.url, 'category');
  if (categoryFilter) {
    filtered = filtered.filter((t) => t.category === categoryFilter);
  }

  const sourceFilter = readStringParam(req.url, 'source');
  if (sourceFilter) {
    filtered = filtered.filter((t) => t.source === sourceFilter);
  }

  const count = filtered.length;
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  const results = filtered.slice(start, start + pageSize);

  const base = new URL(req.url.includes('http') ? req.url : `http://local.invalid${req.url}`);
  base.pathname = base.pathname.replace(/\/?$/, '/');
  const setLink = (p: number): string => {
    const u = new URL(base.toString());
    u.searchParams.set('page', String(p));
    u.searchParams.set('page_size', String(pageSize));
    if (year != null) {
      u.searchParams.set('year', String(year));
    } else {
      u.searchParams.delete('year');
    }
    if (month != null) {
      u.searchParams.set('month', String(month));
    } else {
      u.searchParams.delete('month');
    }
    if (categoryFilter) {
      u.searchParams.set('category', categoryFilter);
    }
    if (sourceFilter) {
      u.searchParams.set('source', sourceFilter);
    }
    return u.toString();
  };

  const nextLink = safePage < totalPages ? setLink(safePage + 1) : null;
  const prevLink = safePage > 1 ? setLink(safePage - 1) : null;

  return of(
    new HttpResponse({
      status: 200,
      body: {
        count,
        next: nextLink,
        previous: prevLink,
        results,
      },
    }),
  );
};

function readStringParam(url: string, key: string): string | undefined {
  try {
    const u = new URL(url.includes('http') ? url : `http://local.invalid${url}`);
    const raw = u.searchParams.get(key);
    return raw && raw !== '' ? raw : undefined;
  } catch {
    return undefined;
  }
}
