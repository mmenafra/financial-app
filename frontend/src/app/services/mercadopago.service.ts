import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { of } from 'rxjs';
import { map } from 'rxjs/operators';
import type { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type { MlItem, MpPayment, MpPaymentSearchResponse } from '../models/mercadopago.model';

@Injectable({ providedIn: 'root' })
export class MercadoPagoService {
  private readonly http = inject(HttpClient);

  private baseUrl(): string {
    return `${environment.apiUrl}/api/mercadopago/transactions/`;
  }

  getPayments(offset = 0, limit = 30): Observable<MpPaymentSearchResponse> {
    const params = new HttpParams().set('offset', String(offset)).set('limit', String(limit));
    return this.http.get<MpPaymentSearchResponse>(this.baseUrl(), { params });
  }

  getPayment(paymentId: string | number): Observable<MpPayment> {
    const id = String(paymentId).trim();
    return this.http.get<MpPayment>(`${this.baseUrl()}${encodeURIComponent(id)}/`);
  }

  /**
   * Fetches MercadoLibre item details via the backend proxy
   * (GET /api/mercadopago/items/?ids=…), which adds the server-side auth token.
   * The ML batch endpoint returns [{code, body}] — only 200 entries are usable.
   */
  getItems(ids: string[]): Observable<MlItem[]> {
    if (ids.length === 0) {
      return of([]);
    }
    const url = `${environment.apiUrl}/api/mercadopago/items/`;
    const params = new HttpParams().set('ids', ids.join(','));
    return this.http
      .get<{ code: number; body: MlItem }[]>(url, { params })
      .pipe(map((results) => results.filter((r) => r.code === 200).map((r) => r.body)));
  }
}
