import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { BehaviorSubject, catchError, filter, switchMap, take, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

let isRefreshing = false;
const refreshDone$ = new BehaviorSubject<string | null>(null);

/** Auth endpoints must never be retried to avoid infinite loops. */
function isAuthUrl(url: string): boolean {
  return url.includes('/api/auth/');
}

export const tokenRefreshInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError((err: unknown) => {
      if (
        !(err instanceof HttpErrorResponse) ||
        err.status !== 401 ||
        isAuthUrl(req.url) ||
        !auth.getRefreshToken()
      ) {
        return throwError(() => err);
      }

      if (isRefreshing) {
        return refreshDone$.pipe(
          filter((token): token is string => token !== null),
          take(1),
          switchMap((token) =>
            next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })),
          ),
        );
      }

      isRefreshing = true;
      refreshDone$.next(null);

      return auth.refreshAccessToken().pipe(
        switchMap((res) => {
          isRefreshing = false;
          refreshDone$.next(res.access);
          return next(req.clone({ setHeaders: { Authorization: `Bearer ${res.access}` } }));
        }),
        catchError((refreshErr) => {
          isRefreshing = false;
          refreshDone$.next(null);
          auth.clearTokens();
          router.navigate(['']);
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
