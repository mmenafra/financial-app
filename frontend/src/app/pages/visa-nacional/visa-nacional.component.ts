import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  HostListener,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';

import { ImportModalComponent } from '../../components/import-modal/import-modal.component';
import { RecurringPatternModalComponent } from '../../components/recurring-pattern-modal/recurring-pattern-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import { TransactionEditModalComponent } from '../../components/transaction-edit-modal/transaction-edit-modal.component';
import { TransactionMetadataModalComponent } from '../../components/transaction-metadata-modal/transaction-metadata-modal.component';
import type {
  Category,
  RecurringPattern,
  Transaction,
  VisaMonthlyTotal,
  VisaNacionalStatement,
} from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

type TimelineTab = 'all' | 'subscriptions' | 'installments';

interface TimelineRow {
  id: string;
  dateLabel: string;
  title: string;
  subtitle: string;
  /** Amount in major units (e.g. 19990). */
  amount: number;
  /** ISO 4217 currency code. */
  currency: string;
  /** Derived from persisted `matched_recurring_pattern`. */
  isSubscription: boolean;
  isInstallment: boolean;
  categoryLabel: string;
  categoryColor: string;
}

interface ChartBarPoint {
  total: number;
  label: string;
}

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

/** Multi-payment installments only; 1/1 is a single charge, not shown as installment. */
function isMultiInstallment(
  current: number | null | undefined,
  total: number | null | undefined,
): boolean {
  if (current == null || total == null) {
    return false;
  }
  return !(current === 1 && total === 1);
}

@Component({
  selector: 'app-visa-nacional',
  standalone: true,
  imports: [
    CommonModule,
    ImportModalComponent,
    SidebarComponent,
    TopNavComponent,
    TransactionEditModalComponent,
    TransactionMetadataModalComponent,
    RecurringPatternModalComponent,
  ],
  templateUrl: './visa-nacional.component.html',
  styleUrl: './visa-nacional.component.scss',
})
export class VisaNacionalComponent {
  private readonly destroyRef = inject(DestroyRef);
  private readonly transactionService = inject(TransactionService);
  private vnTimelineSub: Subscription | null = null;

  constructor() {
    this.transactionService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((cats) => this.categories.set(cats));

    this.transactionService
      .getRecurringPatterns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((pats) => this.recurringPatterns.set(pats));

    this.destroyRef.onDestroy(() => this.vnTimelineSub?.unsubscribe());

    this.loadTimeline();
  }

  protected readonly categories = signal<Category[]>([]);
  protected readonly recurringPatterns = signal<RecurringPattern[]>([]);
  protected readonly transactions = signal<Transaction[]>([]);
  protected readonly currentStatement = signal<VisaNacionalStatement | null>(null);
  protected readonly monthlyTotals = signal<VisaMonthlyTotal[]>([]);
  protected readonly timelineLoading = signal(false);
  protected readonly timelineError = signal<string | null>(null);

  protected readonly categoriesById = computed(() => {
    const m = new Map<string, Category>();
    for (const c of this.categories()) {
      m.set(c.id, c);
    }
    return m;
  });

  protected readonly importModalOpen = signal(false);
  protected readonly importVisaNacionalSubmit = (file: File) =>
    this.transactionService.importVisaNacional(file);

  protected readonly selectedYear = signal(new Date().getFullYear());
  protected readonly selectedMonth = signal(new Date().getMonth() + 1);

  protected readonly timelineTab = signal<TimelineTab>('all');
  protected readonly openMenuId = signal<string | null>(null);
  protected readonly editTarget = signal<Transaction | null>(null);
  protected readonly metadataTarget = signal<Transaction | null>(null);
  protected readonly recurringPatternTarget = signal<Transaction | null>(null);

  protected readonly chartBars = computed((): ChartBarPoint[] => {
    return this.monthlyTotals().map((bucket) => ({
      total: Number(bucket.total),
      label: `${MONTH_SHORT[bucket.month - 1]} '${String(bucket.year).slice(-2)}`,
    }));
  });

  protected readonly barChartSeries = computed(() => this.chartBars().map((b) => b.total));

  /** Compares calendar-month spend (last two chart buckets). Hidden when a billing statement is loaded. */
  protected readonly vsLastMonthPct = computed((): number | null => {
    if (this.currentStatement() !== null) {
      return null;
    }
    const totals = this.monthlyTotals();
    if (totals.length < 2) {
      return null;
    }
    const cur = Number(totals[totals.length - 1]?.total ?? NaN);
    const prev = Number(totals[totals.length - 2]?.total ?? NaN);
    if (Number.isNaN(cur) || Number.isNaN(prev)) {
      return null;
    }
    if (prev === 0) {
      return cur === 0 ? 0 : 100;
    }
    return ((cur - prev) / prev) * 100;
  });

  /**
   * When a billing statement exists: PDF statement total.
   * Otherwise: sum of expense rows in the list (legacy months have no statement row).
   */
  protected readonly periodExpenseTotal = computed(() => {
    const st = this.currentStatement();
    if (st) {
      return Number(st.total_amount);
    }
    let sum = 0;
    for (const t of this.transactions()) {
      if (t.direction === 'EXPENSE') {
        sum += Number(t.amount);
      }
    }
    return sum;
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

  protected readonly timelineRows = computed((): TimelineRow[] => {
    const cmap = this.categoriesById();
    const sorted = [...this.transactions()].sort(
      (a, b) =>
        calendarDateKey(a).localeCompare(calendarDateKey(b)) ||
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
    return sorted.map((tx) => this.transactionToRow(tx, cmap));
  });

  protected readonly filteredTimeline = computed(() => {
    const tab = this.timelineTab();
    const rows = this.timelineRows();
    if (tab === 'subscriptions') {
      return rows.filter((r) => r.isSubscription);
    }
    if (tab === 'installments') {
      return rows.filter((r) => r.isInstallment);
    }
    return rows;
  });

  protected readonly barMax = computed(() =>
    Math.max(1, ...this.barChartSeries().map((v) => Number(v))),
  );

  protected readonly chartAriaLabel = computed(() => {
    const y = this.selectedYear();
    const m = this.selectedMonth();
    return `Twelve-month Visa Nacional expense totals (CLP), ending ${MONTH_SHORT[m - 1]} ${y}.`;
  });

  protected readonly periodRangeLabel = computed(() => {
    const st = this.currentStatement();
    if (st) {
      const p1 = new Date(`${st.period_end}T12:00:00`);
      const b = `${MONTH_SHORT[p1.getMonth()]} ${pad2(p1.getDate())}, ${p1.getFullYear()}`.toUpperCase();
      return `STATEMENT CLOSING: ${b}`;
    }
    const y = this.selectedYear();
    const m = this.selectedMonth();
    const lastDay = new Date(y, m, 0).getDate();
    const mon = MONTH_SHORT[m - 1].toUpperCase();
    return `CURRENT PERIOD: ${mon} 01 - ${mon} ${pad2(lastDay)}, ${y}`;
  });

  protected readonly highlightMonthIndex = computed(() =>
    Math.max(0, this.chartBars().length - 1),
  );

  private transactionToRow(tx: Transaction, cmap: Map<string, Category>): TimelineRow {
    const cat = tx.category ? cmap.get(tx.category) : undefined;
    const key = calendarDateKey(tx);
    const [, m, d] = key.split('-').map(Number);
    const dateLabel = `${MONTH_SHORT[m - 1]} ${pad2(d)}`.toUpperCase();
    const isSubscription = tx.matched_recurring_pattern != null;
    const isInstallment = Boolean(
      tx.is_installment &&
        isMultiInstallment(tx.installment_current, tx.installment_total),
    );
    const parts: string[] = [];
    if (isSubscription) {
      parts.push('Online Subscription');
    }
    if (isInstallment) {
      parts.push(
        `Installment ${tx.installment_current} of ${tx.installment_total}`,
      );
    }
    return {
      id: tx.id,
      dateLabel,
      title: tx.description,
      subtitle: parts.join(' · '),
      amount: Number(tx.amount),
      currency: tx.currency,
      isSubscription,
      isInstallment,
      categoryLabel: cat?.name ?? 'Uncategorized',
      categoryColor: cat?.color ?? '#94a3b8',
    };
  }

  protected barHeightPercent(value: number): number {
    return (value / this.barMax()) * 100;
  }

  /** Tooltip label for bar segment (CLP). */
  protected formatChartBarValue(value: number): string {
    return this.formatClp(value);
  }

  protected formatVsLastMonthLabel(pct: number): string {
    const sign = pct > 0 ? '+' : '';
    return `${sign}${pct.toFixed(1)}%`;
  }

  protected formatClp(amount: number): string {
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency: 'CLP',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  }

  protected formatMoney(amount: number, currency: string): string {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
      }).format(amount);
    } catch {
      return `${amount} ${currency}`;
    }
  }

  protected categoryBadgeStyles(row: TimelineRow): Record<string, string> {
    const hex = row.categoryColor || '#94a3b8';
    return {
      'background-color': `${hex}22`,
      color: hex,
      'border-color': `${hex}44`,
    };
  }

  protected onMonthChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    if (!Number.isNaN(v)) {
      this.selectedMonth.set(v);
      this.loadTimeline();
    }
  }

  protected onYearChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    if (!Number.isNaN(v)) {
      this.selectedYear.set(v);
      this.loadTimeline();
    }
  }

  protected setTimelineTab(tab: TimelineTab): void {
    this.timelineTab.set(tab);
  }

  protected openImportModal(): void {
    this.importModalOpen.set(true);
  }

  protected closeImportModal(): void {
    this.importModalOpen.set(false);
  }

  protected onVisaImportDone(): void {
    this.loadTimeline();
    this.transactionService.getRecurringPatterns().subscribe((pats) => this.recurringPatterns.set(pats));
  }

  private loadTimeline(): void {
    this.vnTimelineSub?.unsubscribe();
    this.timelineLoading.set(true);
    this.timelineError.set(null);
    this.vnTimelineSub = this.transactionService
      .getVisaNacionalDashboard(this.selectedYear(), this.selectedMonth())
      .subscribe({
        next: (body) => {
          this.currentStatement.set(body.statement);
          this.transactions.set(body.transactions);
          this.monthlyTotals.set(body.monthly_totals);
          this.timelineLoading.set(false);
        },
        error: () => {
          this.timelineLoading.set(false);
          this.timelineError.set('Could not load Visa Nacional dashboard.');
        },
      });
  }

  @HostListener('document:click')
  protected closeMenus(): void {
    this.openMenuId.set(null);
  }

  protected toggleTimelineMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected onEditRow(row: TimelineRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    const t = this.transactions().find((x) => x.id === row.id);
    if (t) {
      this.editTarget.set(t);
    }
  }

  protected onEditDismissed(): void {
    this.editTarget.set(null);
  }

  protected onEditSaved(): void {
    this.editTarget.set(null);
    this.loadTimeline();
    this.transactionService.getRecurringPatterns().subscribe((pats) => this.recurringPatterns.set(pats));
  }

  protected onMetaDataRow(row: TimelineRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    const t = this.transactions().find((x) => x.id === row.id);
    if (t) {
      this.metadataTarget.set(t);
    }
  }

  protected onCreateRecurringFromRow(row: TimelineRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    const t = this.transactions().find((x) => x.id === row.id);
    if (t) {
      this.recurringPatternTarget.set(t);
    }
  }

  protected onRecurringPatternDismissed(): void {
    this.recurringPatternTarget.set(null);
  }

  protected onRecurringPatternCreated(): void {
    this.recurringPatternTarget.set(null);
    this.loadTimeline();
    this.transactionService.getRecurringPatterns().subscribe((pats) => this.recurringPatterns.set(pats));
  }

  protected onMetadataDismissed(): void {
    this.metadataTarget.set(null);
  }
}

function calendarDateKey(t: Transaction): string {
  return t.transaction_date ?? t.created_at.slice(0, 10);
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}