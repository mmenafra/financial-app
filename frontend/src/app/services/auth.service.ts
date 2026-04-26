import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

import { environment } from '../../environments/environment';

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

const ACCESS_KEY = 'auth_access';
const REFRESH_KEY = 'auth_refresh';

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
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(ACCESS_KEY, tokens.access);
    storage.setItem(REFRESH_KEY, tokens.refresh);
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  }

  signOut(): void {
    this.clearTokens();
  }

  getAccessToken(): string | null {
    return sessionStorage.getItem(ACCESS_KEY) ?? localStorage.getItem(ACCESS_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }
}
