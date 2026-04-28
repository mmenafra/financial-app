import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

/** GET /api/auth/profile/ — credential value is never returned. */
export interface UserProfileResponse {
  id: string;
  created_at: string;
  updated_at: string;
  has_gemini_key: boolean;
}

@Injectable({ providedIn: 'root' })
export class UserProfileService {
  private readonly http = inject(HttpClient);

  getProfile(): Observable<UserProfileResponse> {
    return this.http.get<UserProfileResponse>(`${environment.apiUrl}/api/auth/profile/`);
  }

  /** Sends key to backend only over HTTPS in production; no local persistence. */
  saveGeminiApiKey(geminiApiKey: string): Observable<UserProfileResponse> {
    return this.http.patch<UserProfileResponse>(`${environment.apiUrl}/api/auth/profile/`, {
      gemini_api_key: geminiApiKey,
    });
  }
}
