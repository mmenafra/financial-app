import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type { MpPayment, MpPaymentSearchResponse } from '../models/mercadopago.model';

@Injectable({ providedIn: 'root' })
export class MercadoPagoService {
  private readonly http = inject(HttpClient);

  private baseUrl(): string {
    return `${environment.apiUrl}/api/mercadopago/transactions/`;
  }

  getPayments(offset = 0, limit = 30): Observable<MpPaymentSearchResponse> {
    const params = new HttpParams()
      .set('offset', String(offset))
      .set('limit', String(limit));
    return this.http.get<MpPaymentSearchResponse>(this.baseUrl(), { params });
  }

  getPayment(paymentId: string | number): Observable<MpPayment> {
    const id = String(paymentId).trim();
    return this.http.get<MpPayment>(`${this.baseUrl()}${encodeURIComponent(id)}/`);
  }
}
