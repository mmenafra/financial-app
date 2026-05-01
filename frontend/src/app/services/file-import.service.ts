import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type { FileImportListResponse, FileImportRerunResponse } from '../models/file-import.model';

@Injectable({ providedIn: 'root' })
export class FileImportService {
  private readonly http = inject(HttpClient);

  list(page = 1, pageSize = 20): Observable<FileImportListResponse> {
    const params = new HttpParams().set('page', String(page)).set('page_size', String(pageSize));
    return this.http.get<FileImportListResponse>(`${environment.apiUrl}/api/file-imports/`, {
      params,
    });
  }

  rerun(id: string): Observable<FileImportRerunResponse> {
    return this.http.post<FileImportRerunResponse>(
      `${environment.apiUrl}/api/file-imports/${id}/re-run/`,
      {},
    );
  }
}
