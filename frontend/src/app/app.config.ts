import {
  ApplicationConfig,
  isDevMode,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideEffects } from '@ngrx/effects';
import { provideState, provideStore } from '@ngrx/store';
import { provideStoreDevtools } from '@ngrx/store-devtools';
import { provideRouter, withEnabledBlockingInitialNavigation } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';

import { authInterceptor } from './interceptors/auth.interceptor';
import { tokenRefreshInterceptor } from './interceptors/token-refresh.interceptor';
import { mockTransactionsInterceptor } from './interceptors/mock-transactions.interceptor';
import { routes } from './app.routes';
import { AppEffects } from './store/app.effects';
import { TransactionsPageEffects } from './store/transactions-page/transactions-page.effects';
import { transactionsPageFeature } from './store/transactions-page/transactions-page.reducer';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withEnabledBlockingInitialNavigation()),
    provideHttpClient(
      withInterceptors([authInterceptor, tokenRefreshInterceptor, mockTransactionsInterceptor]),
    ),
    provideStore({}),
    provideState(transactionsPageFeature),
    provideEffects([AppEffects, TransactionsPageEffects]),
    provideStoreDevtools({ maxAge: 25, logOnly: !isDevMode() }),
  ],
};
