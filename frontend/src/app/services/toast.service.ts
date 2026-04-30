import { Injectable, signal } from '@angular/core';

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  readonly id: string;
  readonly type: ToastType;
  readonly message: string;
}

const SUCCESS_MS = 3000;
const ERROR_MS = 5000;
const INFO_MS = 3000;

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();
  private idSeq = 0;

  success(message: string): void {
    this.push('success', message, SUCCESS_MS);
  }

  error(message: string): void {
    this.push('error', message, ERROR_MS);
  }

  info(message: string): void {
    this.push('info', message, INFO_MS);
  }

  dismiss(id: string): void {
    const t = this.timers.get(id);
    if (t) {
      clearTimeout(t);
      this.timers.delete(id);
    }
    this.toasts.update((list) => list.filter((x) => x.id !== id));
  }

  private push(type: ToastType, message: string, durationMs: number): void {
    const id = `toast-${++this.idSeq}`;
    this.toasts.update((list) => [...list, { id, type, message }]);
    const timerId = setTimeout(() => this.dismiss(id), durationMs);
    this.timers.set(id, timerId);
  }
}
