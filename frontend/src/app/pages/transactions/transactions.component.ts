import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { Category, Source, Transaction } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

const PAGE_SIZE = 10;
const CONNECTED_SOURCES = 4;
const AGG_PAGE_SIZE = 100;

@Component({
  selector: 'app-transactions',
  standalone: true,
  imports: [CommonModule, SidebarComponent, TopNavComponent],
  templateUrl: './transactions.component.html',
  styleUrl: './transactions.component.scss',
})
export class TransactionsComponent {
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly connectedSources = CONNECTED_SOURCES;

  protected readonly selectedYear = signal(new Date().getFullYear());
  protected readonly selectedMonth = signal(new Date().getMonth() + 1);
  protected readonly currentPage = signal(1);

  protected readonly categories = signal<Category[]>([]);
  protected readonly transactions = signal<Transaction[]>([]);
  protected readonly totalCount = signal(0);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly filterOpen = signal(false);
  protected readonly filterCategoryId = signal<string | undefined>(undefined);
  protected readonly filterSource = signal<Source | undefined>(undefined);

  protected readonly openMenuId = signal<string | null>(null);

  protected readonly totalSpentThisMonth = signal(0);
  protected readonly trendVsPrevMonthPct = signal<number | null>(null);
  protected readonly trendSpentLess = signal<boolean | null>(null);

  protected readonly categoryById = computed(() => {
    const map = new Map<string, Category>();
    for (const c of this.categories()) {
      map.set(c.id, c);
    }
    return map;
  });

  protected readonly monthOptions = [
    { value: 1, label: 'January' },
    { value: 2, label: 'February' },
    { value: 3, label: 'March' },
    { value: 4, label: 'April' },
    { value: 5, label: 'May' },
    { value: 6, label: 'June' },
    { value: 7, label: 'July' },
    { value: 8, label: 'August' },
    { value: 9, label: 'September' },
    { value: 10, label: 'October' },
    { value: 11, label: 'November' },
    { value: 12, label: 'December' },
  ];

  protected readonly yearOptions = (() => {
    const y = new Date().getFullYear();
    return Array.from({ length: 7 }, (_, i) => y - 3 + i);
  })();

  constructor() {
    this.reload();
  }

  protected reload(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    const y = this.selectedYear();
    const m = this.selectedMonth();
    const prevYear = m === 1 ? y - 1 : y;
    const prevMonth = m === 1 ? 12 : m - 1;
    const page = this.currentPage();
    const cat = this.filterCategoryId();
    const src = this.filterSource();

    const baseFilters = { year: y, month: m, category: cat, source: src };
    const prevFilters = { year: prevYear, month: prevMonth, category: cat, source: src };

    forkJoin({
      categories: this.transactionService.getCategories(),
      page: this.transactionService.getTransactions({
        ...baseFilters,
        page,
        pageSize: PAGE_SIZE,
      }),
      monthAgg: this.transactionService.getTransactions({
        ...baseFilters,
        page: 1,
        pageSize: AGG_PAGE_SIZE,
      }),
      prevAgg: this.transactionService.getTransactions({
        ...prevFilters,
        page: 1,
        pageSize: AGG_PAGE_SIZE,
      }),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ categories, page: p, monthAgg, prevAgg }) => {
          this.categories.set(categories);
          this.transactions.set(p.results);
          this.totalCount.set(p.count);

          const spentThis = sumExpenses(monthAgg.results);
          const spentPrev = sumExpenses(prevAgg.results);
          this.totalSpentThisMonth.set(spentThis);

          if (spentPrev <= 0) {
            this.trendVsPrevMonthPct.set(null);
            this.trendSpentLess.set(null);
          } else if (spentThis < spentPrev) {
            const pct = ((spentPrev - spentThis) / spentPrev) * 100;
            this.trendVsPrevMonthPct.set(Math.round(pct * 10) / 10);
            this.trendSpentLess.set(true);
          } else if (spentThis > spentPrev) {
            const pct = ((spentThis - spentPrev) / spentPrev) * 100;
            this.trendVsPrevMonthPct.set(Math.round(pct * 10) / 10);
            this.trendSpentLess.set(false);
          } else {
            this.trendVsPrevMonthPct.set(0);
            this.trendSpentLess.set(null);
          }

          this.isLoading.set(false);
        },
        error: () => {
          this.loadError.set('Could not load transactions. Try again.');
          this.isLoading.set(false);
        },
      });
  }

  protected onYearChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    this.selectedYear.set(v);
    this.currentPage.set(1);
    this.reload();
  }

  protected onMonthChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    this.selectedMonth.set(v);
    this.currentPage.set(1);
    this.reload();
  }

  protected toggleFilters(): void {
    this.filterOpen.update((o) => !o);
  }

  protected onFilterCategory(event: Event): void {
    const v = (event.target as HTMLSelectElement).value;
    this.filterCategoryId.set(v || undefined);
  }

  protected onFilterSource(event: Event): void {
    const v = (event.target as HTMLSelectElement).value as Source | '';
    this.filterSource.set(v || undefined);
  }

  protected applyFilters(): void {
    this.currentPage.set(1);
    this.filterOpen.set(false);
    this.reload();
  }

  protected clearFilters(): void {
    this.filterCategoryId.set(undefined);
    this.filterSource.set(undefined);
    this.currentPage.set(1);
    this.reload();
  }

  protected goToPage(p: number): void {
    const totalPages = Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
    const next = Math.min(Math.max(1, p), totalPages);
    this.currentPage.set(next);
    this.reload();
  }

  protected pageNumbers(): (number | 'ellipsis')[] {
    const totalPages = Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
    const cur = this.currentPage();
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages = new Set<number>();
    pages.add(1);
    pages.add(totalPages);
    for (let i = cur - 1; i <= cur + 1; i++) {
      if (i >= 1 && i <= totalPages) {
        pages.add(i);
      }
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const out: (number | 'ellipsis')[] = [];
    for (let i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
        out.push('ellipsis');
      }
      out.push(sorted[i]);
    }
    return out;
  }

  protected showingFrom(): number {
    if (this.totalCount() === 0) {
      return 0;
    }
    return (this.currentPage() - 1) * PAGE_SIZE + 1;
  }

  protected showingTo(): number {
    return Math.min(this.currentPage() * PAGE_SIZE, this.totalCount());
  }

  protected totalPages(): number {
    return Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
  }

  protected formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  protected formatMoney(amount: string, currency: string): string {
    const n = Number(amount);
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
      }).format(n);
    } catch {
      return `${currency} ${n.toFixed(2)}`;
    }
  }

  protected displayAmount(t: Transaction): string {
    const formatted = this.formatMoney(t.amount, t.currency);
    if (t.direction === 'INCOME') {
      return `+${formatted}`;
    }
    return `-${formatted}`;
  }

  protected amountClass(t: Transaction): string {
    return t.direction === 'INCOME' ? 'amount-income' : 'amount-expense';
  }

  protected sourceLabel(source: Source): string {
    const labels: Record<Source, string> = {
      BANK_ACCOUNT: 'Bank Account',
      CREDIT_CARD_NATIONAL: 'Visa National',
      CREDIT_CARD_INTERNATIONAL: 'Visa International',
      MERCADOPAGO: 'MercadoPago',
    };
    return labels[source];
  }

  protected sourceIcon(source: Source): string {
    return source === 'BANK_ACCOUNT' ? 'account_balance' : 'credit_card';
  }

  protected categoryLabel(t: Transaction): string {
    if (!t.category) {
      return 'Uncategorized';
    }
    return this.categoryById().get(t.category)?.name ?? 'Category';
  }

  protected categoryStyles(t: Transaction): Record<string, string> {
    const cat = t.category ? this.categoryById().get(t.category) : undefined;
    const hex = cat?.color ?? '#94a3b8';
    return {
      'background-color': `${hex}22`,
      color: hex,
      'border-color': `${hex}44`,
    };
  }

  protected categoryIcon(t: Transaction): string {
    const cat = t.category ? this.categoryById().get(t.category) : undefined;
    return cat?.icon ?? 'receipt';
  }

  @HostListener('document:click')
  protected closeMenu(): void {
    this.openMenuId.set(null);
  }

  protected toggleMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected onEdit(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    // TODO: open edit dialog for t
    console.log('Edit', t);
  }

  protected onDelete(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    // TODO: confirm and delete t
    console.log('Delete', t);
  }

  protected trendText(): string {
    const pct = this.trendVsPrevMonthPct();
    const less = this.trendSpentLess();
    if (pct === null && less === null) {
      return 'No comparison for last month';
    }
    if (less === null && pct === 0) {
      return 'Same as last month';
    }
    if (less === true) {
      return `${pct}% less than last month`;
    }
    return `${pct}% more than last month`;
  }
}

function sumExpenses(rows: Transaction[]): number {
  return rows
    .filter((t) => t.direction === 'EXPENSE')
    .reduce((acc, t) => acc + Number(t.amount), 0);
}
