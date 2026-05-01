import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map, mergeMap, of } from 'rxjs';

import { environment } from '../../environments/environment';
import type {
  BankStatementImportResult,
  Category,
  CreateRecurringPatternPayload,
  CreateTransactionPayload,
  IncomeDashboardResponse,
  PaginatedResponse,
  RecurringPattern,
  Subscription,
  SplitItem,
  Transaction,
  TransactionFilters,
  UpdateTransactionPayload,
  VisaInternationalDashboardResponse,
  VisaNacionalDashboardResponse,
} from '../models/transaction.model';
import { normalizeBankStatementImportResult } from '../utils/normalize-bank-statement-import-result';

@Injectable({ providedIn: 'root' })
export class TransactionService {
  private readonly http = inject(HttpClient);

  getTransactions(filters: TransactionFilters = {}): Observable<PaginatedResponse<Transaction>> {
    let params = new HttpParams();
    if (filters.year != null) {
      params = params.set('year', String(filters.year));
    }
    if (filters.month != null) {
      params = params.set('month', String(filters.month));
    }
    if (filters.category) {
      params = params.set('category', filters.category);
    }
    if (filters.source) {
      params = params.set('source', filters.source);
    }
    if (filters.page != null) {
      params = params.set('page', String(filters.page));
    }
    if (filters.pageSize != null) {
      params = params.set('page_size', String(filters.pageSize));
    }
    return this.http.get<PaginatedResponse<Transaction>>(
      `${environment.apiUrl}/api/transactions/`,
      { params },
    );
  }

  /** Income page: INCOME-only list, monthly aggregates, rolling 12-month chart. */
  getIncome(filters: TransactionFilters = {}): Observable<IncomeDashboardResponse> {
    let params = new HttpParams();
    if (filters.year != null) {
      params = params.set('year', String(filters.year));
    }
    if (filters.month != null) {
      params = params.set('month', String(filters.month));
    }
    if (filters.category) {
      params = params.set('category', filters.category);
    }
    if (filters.source) {
      params = params.set('source', filters.source);
    }
    if (filters.page != null) {
      params = params.set('page', String(filters.page));
    }
    if (filters.pageSize != null) {
      params = params.set('page_size', String(filters.pageSize));
    }
    return this.http.get<IncomeDashboardResponse>(`${environment.apiUrl}/api/income/`, {
      params,
    });
  }

  /**
   * Loads every page for the given filters (page_size capped server-side, e.g. 100).
   * Omits `page` / `pageSize` on `filters` — uses internal paging.
   */
  getAllTransactions(
    filters: Omit<TransactionFilters, 'page' | 'pageSize'>,
  ): Observable<Transaction[]> {
    const pageSize = 100;
    const fetchAccum = (page: number, acc: Transaction[]): Observable<Transaction[]> => {
      return this.getTransactions({ ...filters, page, pageSize }).pipe(
        mergeMap((res) => {
          const combined = acc.concat(res.results);
          if (!res.next) {
            return of(combined);
          }
          return fetchAccum(page + 1, combined);
        }),
      );
    };
    return fetchAccum(1, []);
  }

  /** User recurring patterns (subscriptions rules). */
  getRecurringPatterns(): Observable<RecurringPattern[]> {
    return this.http.get<RecurringPattern[]>(`${environment.apiUrl}/api/recurring-patterns/`);
  }

  createRecurringPattern(payload: CreateRecurringPatternPayload): Observable<RecurringPattern> {
    return this.http.post<RecurringPattern>(
      `${environment.apiUrl}/api/recurring-patterns/`,
      payload,
    );
  }

  /** Recurring matches on latest Visa Nacional and Visa International statements only. */
  getSubscriptions(): Observable<Subscription[]> {
    return this.http.get<Subscription[]>(`${environment.apiUrl}/api/subscriptions/`);
  }

  /** Categories list is unpaginated on the backend (no pagination class on `CategoryViewSet`). */
  getCategories(): Observable<Category[]> {
    return this.http.get<Category[]>(`${environment.apiUrl}/api/categories/`);
  }

  importBankStatement(file: File): Observable<BankStatementImportResult> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<BankStatementImportResult>(
        `${environment.apiUrl}/api/transactions/import-bank-statement/`,
        body,
      )
      .pipe(map(normalizeBankStatementImportResult));
  }

  importVisaInternational(file: File): Observable<BankStatementImportResult> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<BankStatementImportResult>(
        `${environment.apiUrl}/api/transactions/import-visa-international/`,
        body,
      )
      .pipe(map(normalizeBankStatementImportResult));
  }

  importVisaNacional(file: File): Observable<BankStatementImportResult> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<BankStatementImportResult>(
        `${environment.apiUrl}/api/transactions/import-visa-national/`,
        body,
      )
      .pipe(map(normalizeBankStatementImportResult));
  }

  /** Visa International page: statement, transactions, and 12 rolling monthly totals. */
  getVisaInternationalDashboard(
    year: number,
    month: number,
  ): Observable<VisaInternationalDashboardResponse> {
    const params = new HttpParams().set('year', String(year)).set('month', String(month));
    return this.http.get<VisaInternationalDashboardResponse>(
      `${environment.apiUrl}/api/visa-international/dashboard/`,
      { params },
    );
  }

  /** Visa Nacional page: statement, transactions, and 12 rolling monthly totals (CLP). */
  getVisaNacionalDashboard(
    year: number,
    month: number,
  ): Observable<VisaNacionalDashboardResponse> {
    const params = new HttpParams().set('year', String(year)).set('month', String(month));
    return this.http.get<VisaNacionalDashboardResponse>(
      `${environment.apiUrl}/api/visa-nacional/dashboard/`,
      { params },
    );
  }

  createTransaction(payload: CreateTransactionPayload): Observable<Transaction> {
    return this.http.post<Transaction>(
      `${environment.apiUrl}/api/transactions/`,
      payload,
    );
  }

  splitTransaction(id: string, items: SplitItem[]): Observable<Transaction[]> {
    return this.http.post<Transaction[]>(
      `${environment.apiUrl}/api/transactions/${id}/split/`,
      { items },
    );
  }

  updateTransaction(id: string, payload: UpdateTransactionPayload): Observable<Transaction> {
    return this.http.patch<Transaction>(
      `${environment.apiUrl}/api/transactions/${id}/`,
      payload,
    );
  }

  deleteTransaction(id: string): Observable<void> {
    return this.http.delete<void>(
      `${environment.apiUrl}/api/transactions/${id}/`,
    );
  }
}
