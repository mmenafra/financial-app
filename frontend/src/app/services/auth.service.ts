import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

import { environment } from '../../environments/environment';

export interface TokenRefreshResponse {
  access: string;
  refresh?: string;
}

export interface SignInPayload {
  username: string;
  password: string;
}

export interface SignUpPayload {
  username: string;
  email: string;
  password: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface AuthUser {
  id: number;
  username: string;
  email: string;
}

export interface SignInResponse {
  user: AuthUser;
  tokens: AuthTokens;
}

/** Storage keys — exported for cross-tab sync (see App). */
export const AUTH_ACCESS_STORAGE_KEY = 'auth_access';
export const AUTH_REFRESH_STORAGE_KEY = 'auth_refresh';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);

  signIn(payload: SignInPayload, remember: boolean): Observable<SignInResponse> {
    return this.http
      .post<SignInResponse>(`${environment.apiUrl}/api/auth/signin/`, payload)
      .pipe(tap((res) => this.storeTokens(res.tokens, remember)));
  }

  signUp(payload: SignUpPayload, remember: boolean): Observable<SignInResponse> {
    return this.http
      .post<SignInResponse>(`${environment.apiUrl}/api/auth/signup/`, payload)
      .pipe(tap((res) => this.storeTokens(res.tokens, remember)));
  }

  loginWithGoogle(idToken: string, remember: boolean): Observable<SignInResponse> {
    return this.http
      .post<SignInResponse>(`${environment.apiUrl}/api/auth/google/`, {
        id_token: idToken,
      })
      .pipe(tap((res) => this.storeTokens(res.tokens, remember)));
  }

  storeTokens(tokens: AuthTokens, remember: boolean): void {
    this.clearTokens();
    if (remember) {
      localStorage.setItem(AUTH_ACCESS_STORAGE_KEY, tokens.access);
      localStorage.setItem(AUTH_REFRESH_STORAGE_KEY, tokens.refresh);
    } else {
      /**
       * Session login: refresh in localStorage so other tabs can obtain an access token;
       * access stays in sessionStorage (tab-scoped).
       */
      localStorage.setItem(AUTH_REFRESH_STORAGE_KEY, tokens.refresh);
      sessionStorage.setItem(AUTH_ACCESS_STORAGE_KEY, tokens.access);
    }
  }

  clearTokens(): void {
    localStorage.removeItem(AUTH_ACCESS_STORAGE_KEY);
    localStorage.removeItem(AUTH_REFRESH_STORAGE_KEY);
    sessionStorage.removeItem(AUTH_ACCESS_STORAGE_KEY);
    sessionStorage.removeItem(AUTH_REFRESH_STORAGE_KEY);
  }

  signOut(): void {
    this.clearTokens();
  }

  getAccessToken(): string | null {
    return (
      sessionStorage.getItem(AUTH_ACCESS_STORAGE_KEY) ??
      localStorage.getItem(AUTH_ACCESS_STORAGE_KEY)
    );
  }

  getRefreshToken(): string | null {
    return (
      sessionStorage.getItem(AUTH_REFRESH_STORAGE_KEY) ??
      localStorage.getItem(AUTH_REFRESH_STORAGE_KEY)
    );
  }

  refreshAccessToken(): Observable<TokenRefreshResponse> {
    const refresh = this.getRefreshToken();
    return this.http
      .post<TokenRefreshResponse>(`${environment.apiUrl}/api/auth/token/refresh/`, { refresh })
      .pipe(
        tap((res) => {
          const accessInLocal = !!localStorage.getItem(AUTH_ACCESS_STORAGE_KEY);
          if (accessInLocal) {
            localStorage.setItem(AUTH_ACCESS_STORAGE_KEY, res.access);
            if (res.refresh) {
              localStorage.setItem(AUTH_REFRESH_STORAGE_KEY, res.refresh);
            }
          } else {
            sessionStorage.setItem(AUTH_ACCESS_STORAGE_KEY, res.access);
            if (res.refresh) {
              localStorage.setItem(AUTH_REFRESH_STORAGE_KEY, res.refresh);
            }
          }
        }),
      );
  }

  /** True if we have any persisted session (access and/or refresh). */
  isAuthenticated(): boolean {
    return !!this.getAccessToken() || !!this.getRefreshToken();
  }
}
