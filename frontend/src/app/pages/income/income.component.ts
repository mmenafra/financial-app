import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import { TransactionEditModalComponent } from '../../components/transaction-edit-modal/transaction-edit-modal.component';
import { TransactionMetadataModalComponent } from '../../components/transaction-metadata-modal/transaction-metadata-modal.component';
import type {
  Category,
  IncomeDashboardResponse,
  Source,
  Transaction,
  TransactionFilters,
} from '../../models/transaction.model';
import { ToastService } from '../../services/toast.service';
import { TransactionService } from '../../services/transaction.service';

const PAGE_SIZE = 100;

const MONTH_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

const SOURCE_LABELS: Record<Source, string> = {
  BANK_ACCOUNT: 'Bank Account',
  CREDIT_CARD_NATIONAL: 'Visa National',
  CREDIT_CARD_INTERNATIONAL: 'Visa International',
  MERCADOPAGO: 'MercadoPago',
};

interface ChartBarPoint {
  total: number;
  label: string;
}

@Component({
  selector: 'app-income',
  standalone: true,
  imports: [
    CommonModule,
    SidebarComponent,
    TopNavComponent,
    TransactionEditModalComponent,
    TransactionMetadataModalComponent,
  ],
  templateUrl: './income.component.html',
  styleUrl: './income.component.scss',
})
export class IncomeComponent {
  private readonly transactionService = inject(TransactionService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;

  protected readonly currentPage = signal(1);

  /** Values in the filter panel (edit before Apply). */
  protected readonly draftYear = signal<number | undefined>(undefined);
  protected readonly draftMonth = signal<number | undefined>(undefined);
  protected readonly draftSource = signal<Source | undefined>(undefined);

  /** Values sent to the API (after Apply / Clear / chip remove). */
  protected readonly appliedYear = signal<number | undefined>(undefined);
  protected readonly appliedMonth = signal<number | undefined>(undefined);
  protected readonly appliedSource = signal<Source | undefined>(undefined);

  protected readonly categories = signal<Category[]>([]);
  protected readonly transactions = signal<Transaction[]>([]);
  protected readonly totalCount = signal(0);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly monthlyTotals = signal<IncomeDashboardResponse['monthly_totals']>([]);

  protected readonly filterOpen = signal(false);

  protected readonly openMenuId = signal<string | null>(null);
  protected readonly editTarget = signal<Transaction | null>(null);
  protected readonly metadataTarget = signal<Transaction | null>(null);

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
    return Array.from({ length: 11 }, (_, i) => y - 5 + i);
  })();

  protected readonly chartBars = computed((): ChartBarPoint[] => {
    const raw = this.monthlyTotals() ?? [];
    return raw.map((bucket) => ({
      total: Number(bucket.total),
      label: `${MONTH_SHORT[bucket.month - 1]} '${String(bucket.year).slice(-2)}`,
    }));
  });

  protected readonly barChartSeries = computed(() => this.chartBars().map((b) => b.total));

  protected readonly barMax = computed(() =>
    Math.max(1, ...this.barChartSeries().map((v) => Number(v))),
  );

  private syncDraftFromApplied(): void {
    this.draftYear.set(this.appliedYear());
    this.draftMonth.set(this.appliedMonth());
    this.draftSource.set(this.appliedSource());
  }

  protected readonly chartAriaLabel = computed(() => {
    const y = this.appliedYear();
    const m = this.appliedMonth();
    if (y !== undefined && m !== undefined) {
      return `Twelve-month income totals, ending ${MONTH_SHORT[m - 1]} ${y}.`;
    }
    if (y !== undefined) {
      return `Twelve-month income totals, ending December ${y}.`;
    }
    const d = new Date();
    return `Twelve-month income totals, ending ${MONTH_SHORT[d.getMonth()]} ${d.getFullYear()}.`;
  });

  protected readonly highlightMonthIndex = computed(() => Math.max(0, this.chartBars().length - 1));

  constructor() {
    this.reload();
  }

  private buildApiFilters(): TransactionFilters {
    const out: TransactionFilters = {};
    const y = this.appliedYear();
    const m = this.appliedMonth();
    const src = this.appliedSource();
    if (y !== undefined) {
      out.year = y;
    }
    if (m !== undefined) {
      out.month = m;
    }
    if (src) {
      out.source = src;
    }
    return out;
  }

  protected reload(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    const page = this.currentPage();
    const baseFilters = this.buildApiFilters();

    forkJoin({
      categories: this.transactionService.getCategories(),
      page: this.transactionService.getIncome({
        ...baseFilters,
        page,
        pageSize: PAGE_SIZE,
      }),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ categories, page: p }) => {
          this.categories.set(categories);
          this.transactions.set(p.results);
          this.totalCount.set(p.count);
          this.monthlyTotals.set(p.monthly_totals ?? []);
          this.isLoading.set(false);
        },
        error: () => {
          const msg = 'Could not load income. Try again.';
          this.loadError.set(msg);
          this.toast.error(msg);
          this.isLoading.set(false);
        },
      });
  }

  protected toggleFilters(): void {
    this.filterOpen.update((o) => {
      const next = !o;
      if (next) {
        this.syncDraftFromApplied();
      }
      return next;
    });
  }

  protected onDraftYear(event: Event): void {
    const raw = (event.target as HTMLSelectElement).value;
    if (raw === '') {
      this.draftYear.set(undefined);
      this.draftMonth.set(undefined);
      return;
    }
    this.draftYear.set(Number(raw));
  }

  protected onDraftMonth(event: Event): void {
    const raw = (event.target as HTMLSelectElement).value;
    this.draftMonth.set(raw === '' ? undefined : Number(raw));
  }

  protected onDraftSource(event: Event): void {
    const v = (event.target as HTMLSelectElement).value as Source | '';
    this.draftSource.set(v || undefined);
  }

  protected applyFilters(): void {
    const y = this.draftYear();
    const m = this.draftMonth();
    if (m !== undefined && y === undefined) {
      this.toast.error('Select a year when filtering by month.');
      return;
    }
    this.appliedYear.set(y);
    this.appliedMonth.set(m);
    this.appliedSource.set(this.draftSource());
    this.currentPage.set(1);
    this.filterOpen.set(false);
    this.reload();
  }

  protected clearFilters(): void {
    this.draftYear.set(undefined);
    this.draftMonth.set(undefined);
    this.draftSource.set(undefined);
    this.appliedYear.set(undefined);
    this.appliedMonth.set(undefined);
    this.appliedSource.set(undefined);
    this.currentPage.set(1);
    this.filterOpen.set(false);
    this.reload();
  }

  protected activeYearLabel(): string {
    const y = this.appliedYear();
    return y !== undefined ? String(y) : '';
  }

  protected activeMonthLabel(): string {
    const m = this.appliedMonth();
    if (m === undefined) {
      return '';
    }
    return this.monthOptions.find((o) => o.value === m)?.label ?? String(m);
  }

  protected activeSourceLabel(): string {
    const src = this.appliedSource();
    if (!src) {
      return '';
    }
    return SOURCE_LABELS[src] ?? src;
  }

  protected removeFilter(kind: 'year' | 'month' | 'source'): void {
    if (kind === 'year') {
      this.appliedYear.set(undefined);
      this.appliedMonth.set(undefined);
    } else if (kind === 'month') {
      this.appliedMonth.set(undefined);
    } else {
      this.appliedSource.set(undefined);
    }
    this.syncDraftFromApplied();
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
    const [year, month, day] = iso.slice(0, 10).split('-').map(Number);
    const d = new Date(year, month - 1, day);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  protected formatTransactionCalendarDate(t: Transaction): string {
    const iso = t.transaction_date ?? t.created_at.slice(0, 10);
    return this.formatDate(iso);
  }

  protected displayAmount(t: Transaction): string {
    const n = Number(t.amount);
    const formatted = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
    if (t.direction === 'INCOME') {
      return `+${formatted}`;
    }
    return `-${formatted}`;
  }

  protected amountClass(t: Transaction): string {
    return t.direction === 'INCOME' ? 'amount-income' : 'amount-expense';
  }

  protected sourceLabel(source: Source): string {
    return SOURCE_LABELS[source];
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

  protected barHeightPercent(value: number): number {
    return (value / this.barMax()) * 100;
  }

  protected formatChartBarValue(value: number): string {
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(value);
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
    this.editTarget.set(t);
  }

  protected onEditDismissed(): void {
    this.editTarget.set(null);
  }

  protected onEditSaved(): void {
    this.editTarget.set(null);
    this.toast.success('Changes saved');
    this.reload();
  }

  protected onMetadata(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.metadataTarget.set(t);
  }

  protected onMetadataDismissed(): void {
    this.metadataTarget.set(null);
  }
}
