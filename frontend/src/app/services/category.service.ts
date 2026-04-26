import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type { Category } from '../models/transaction.model';

/** Body for creating or partial-updating a category (mirrors `CategorySerializer` writable fields). */
export interface CategoryWrite {
  name: string;
  parent?: string | null;
  icon?: string | null;
  color?: string | null;
}

@Injectable({ providedIn: 'root' })
export class CategoryService {
  private readonly http = inject(HttpClient);

  getCategories(): Observable<Category[]> {
    return this.http.get<Category[]>(`${environment.apiUrl}/api/categories/`);
  }

  createCategory(data: CategoryWrite): Observable<Category> {
    return this.http.post<Category>(`${environment.apiUrl}/api/categories/`, data);
  }

  updateCategory(id: string, data: Partial<CategoryWrite>): Observable<Category> {
    return this.http.patch<Category>(`${environment.apiUrl}/api/categories/${id}/`, data);
  }

  deleteCategory(id: string): Observable<unknown> {
    return this.http.delete(`${environment.apiUrl}/api/categories/${id}/`);
  }
}
