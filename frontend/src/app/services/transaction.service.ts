import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type {
  Category,
  PaginatedResponse,
  Transaction,
  TransactionFilters,
} from '../models/transaction.model';

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

  /** Categories list is unpaginated on the backend (no pagination class on `CategoryViewSet`). */
  getCategories(): Observable<Category[]> {
    return this.http.get<Category[]>(`${environment.apiUrl}/api/categories/`);
  }
}
