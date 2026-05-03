import { Component, DestroyRef, inject, signal } from '@angular/core';

import { Router, RouterOutlet } from '@angular/router';

import { ToastContainerComponent } from './components/toast-container/toast-container.component';
import {
  AUTH_ACCESS_STORAGE_KEY,
  AUTH_REFRESH_STORAGE_KEY,
  AuthService,
} from './services/auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ToastContainerComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly title = signal('web');

  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    if (typeof globalThis.addEventListener !== 'function') {
      return;
    }
    const onStorage = (e: StorageEvent): void => {
      if (e.storageArea !== localStorage) return;
      if (e.key !== AUTH_REFRESH_STORAGE_KEY && e.key !== AUTH_ACCESS_STORAGE_KEY) return;

      if (e.newValue === null && e.key === AUTH_REFRESH_STORAGE_KEY) {
        this.auth.signOut();
        const path = this.router.url.split('?')[0] || '/';
        const normalized = path === '' ? '/' : path;
        if (!['/', '/login', '/signup'].includes(normalized)) {
          void this.router.navigate(['/']);
        }
        return;
      }

      if (e.newValue === null) return;
      this.redirectGuestsWithSession();
    };
    globalThis.addEventListener('storage', onStorage);
    this.destroyRef.onDestroy(() => globalThis.removeEventListener('storage', onStorage));
  }

  /**
   * When another tab signs in, localStorage is updated and this tab receives `storage`.
   * If we are still on a guest route, go to the dashboard.
   */
  private redirectGuestsWithSession(): void {
    if (!this.auth.isAuthenticated()) return;
    const path = this.router.url.split('?')[0] || '/';
    const normalized = path === '' ? '/' : path;
    if (['/login', '/signup'].includes(normalized) || normalized === '/') {
      void this.router.navigate(['/dashboard'], { replaceUrl: true });
    }
  }
}
