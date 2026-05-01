import { CommonModule } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { RecurringFrequency, Subscription } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

@Component({
  selector: 'app-subscriptions',
  standalone: true,
  imports: [CommonModule, SidebarComponent, TopNavComponent],
  templateUrl: './subscriptions.component.html',
  styleUrl: './subscriptions.component.scss',
})
export class SubscriptionsComponent {
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly items = signal<Subscription[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly totalsByCurrency = computed(() => {
    const rows = this.items();
    const map = new Map<string, number>();
    for (const s of rows) {
      map.set(s.currency, (map.get(s.currency) ?? 0) + Number(s.amount));
    }
    return [...map.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([currency, total]) => ({ currency, total }));
  });

  constructor() {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.transactionService
      .getSubscriptions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => {
          this.items.set(rows);
          this.isLoading.set(false);
        },
        error: () => {
          this.loadError.set('Could not load subscriptions. Try again.');
          this.isLoading.set(false);
        },
      });
  }

  protected formatMoney(amount: number, currency: string): string {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${currency} ${amount.toFixed(2)}`;
    }
  }

  protected frequencyLabel(f: RecurringFrequency): string {
    const labels: Record<RecurringFrequency, string> = {
      DAILY: 'Daily',
      WEEKLY: 'Weekly',
      MONTHLY: 'Monthly',
      YEARLY: 'Yearly',
    };
    return labels[f];
  }

  protected displaySubscriptionAmount(amount: string): string {
    const n = Number(amount);
    const formatted = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
    return `-${formatted}`;
  }

  protected formatMatchedDate(iso: string | null): string {
    if (!iso) {
      return '—';
    }
    const [y, m, d] = iso.split('-').map(Number);
    if (!y || !m || !d) {
      return iso;
    }
    const date = new Date(y, m - 1, d);
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
}
