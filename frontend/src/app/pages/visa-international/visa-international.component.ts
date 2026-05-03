import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';

import { BarChartComponent } from '../../components/bar-chart/bar-chart.component';
import { ImportModalComponent } from '../../components/import-modal/import-modal.component';
import { RecurringPatternModalComponent } from '../../components/recurring-pattern-modal/recurring-pattern-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import { TransactionEditModalComponent } from '../../components/transaction-edit-modal/transaction-edit-modal.component';
import { TransactionMetadataModalComponent } from '../../components/transaction-metadata-modal/transaction-metadata-modal.component';
import type {
  Category,
  Direction,
  RecurringPattern,
  Transaction,
  UpdateTransactionPayload,
  VisaInternationalStatement,
  VisaMonthlyTotal,
} from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';
import { ToastService } from '../../services/toast.service';
import { httpErrorMessage } from '../../utils/transaction-edit';
import { resolveApiFileUrl } from '../../utils/resolve-api-file-url';

type TimelineTab = 'all' | 'subscriptions';

interface TimelineRow {
  id: string;
  dateLabel: string;
  title: string;
  subtitle: string;
  /** Amount in major units (e.g. 19.99). */
  amount: number;
  /** ISO 4217 currency code. */
  currency: string;
  /** Derived from persisted `matched_recurring_pattern`. */
  isSubscription: boolean;
  categoryLabel: string;
  categoryColor: string;
  direction: Direction;
}

interface ChartBarPoint {
  total: number;
  label: string;
}

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

@Component({
  selector: 'app-visa-international',
  standalone: true,
  imports: [
    BarChartComponent,
    CommonModule,
    ImportModalComponent,
    SidebarComponent,
    TopNavComponent,
    TransactionEditModalComponent,
    TransactionMetadataModalComponent,
    RecurringPatternModalComponent,
  ],
  templateUrl: './visa-international.component.html',
  styleUrl: './visa-international.component.scss',
})
export class VisaInternationalComponent {
  private readonly destroyRef = inject(DestroyRef);
  private readonly transactionService = inject(TransactionService);
  private readonly toast = inject(ToastService);
  private viTimelineSub: Subscription | null = null;

  constructor() {
    this.transactionService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((cats) => this.categories.set(cats));

    this.transactionService
      .getRecurringPatterns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((pats) => this.recurringPatterns.set(pats));

    this.destroyRef.onDestroy(() => this.viTimelineSub?.unsubscribe());

    this.loadTimeline();
  }

  protected readonly categories = signal<Category[]>([]);
  protected readonly recurringPatterns = signal<RecurringPattern[]>([]);
  protected readonly transactions = signal<Transaction[]>([]);
  protected readonly currentStatement = signal<VisaInternationalStatement | null>(null);
  /** Resolves `/media/...` against the API base when the SPA is on another origin. */
  protected readonly statementPdfHref = computed(() =>
    resolveApiFileUrl(this.currentStatement()?.uploaded_file_url ?? null),
  );
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
  protected readonly importVisaInternationalSubmit = (file: File) =>
    this.transactionService.importVisaInternational(file);

  protected readonly selectedYear = signal(new Date().getFullYear());
  protected readonly selectedMonth = signal(new Date().getMonth() + 1);

  protected readonly timelineTab = signal<TimelineTab>('all');
  protected readonly openMenuId = signal<string | null>(null);
  protected readonly editTarget = signal<Transaction | null>(null);
  protected readonly editSaving = signal(false);
  protected readonly editServerError = signal<string | null>(null);
  protected readonly metadataTarget = signal<Transaction | null>(null);
  protected readonly recurringPatternTarget = signal<Transaction | null>(null);

  protected readonly chartBars = computed((): ChartBarPoint[] => {
    return this.monthlyTotals().map((bucket) => ({
      total: Number(bucket.total),
      label: `${MONTH_SHORT[bucket.month - 1]} '${String(bucket.year).slice(-2)}`,
    }));
  });

  protected readonly chartLabels = computed(() => this.chartBars().map((b) => b.label));
  protected readonly chartData = computed(() => this.chartBars().map((b) => b.total));
  protected readonly chartValueFormatter = (v: number): string => this.formatUsd(v);

  /** Compares the last two monthly-totals chart buckets (statement totals when available, else 0). */
  protected readonly vsLastMonthPct = computed((): number | null => {
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
   * Otherwise: sum of expense rows in the list (legacy months have no statement row; chart bars are still per closing month).
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
    return rows;
  });

  protected readonly chartAriaLabel = computed(() => {
    const y = this.selectedYear();
    const m = this.selectedMonth();
    return `Twelve-month Visa International expense totals (USD), ending ${MONTH_SHORT[m - 1]} ${y}.`;
  });

  protected readonly periodRangeLabel = computed(() => {
    const st = this.currentStatement();
    if (st) {
      const p0 = new Date(`${st.period_start}T12:00:00`);
      const p1 = new Date(`${st.period_end}T12:00:00`);
      const a = `${MONTH_SHORT[p0.getMonth()]} ${pad2(p0.getDate())}`.toUpperCase();
      const b =
        `${MONTH_SHORT[p1.getMonth()]} ${pad2(p1.getDate())}, ${p1.getFullYear()}`.toUpperCase();
      return `BILLING PERIOD: ${a} – ${b}`;
    }
    const y = this.selectedYear();
    const m = this.selectedMonth();
    const lastDay = new Date(y, m, 0).getDate();
    const mon = MONTH_SHORT[m - 1].toUpperCase();
    return `CURRENT PERIOD: ${mon} 01 - ${mon} ${pad2(lastDay)}, ${y}`;
  });

  /** Last bar in the series is the dashboard’s selected month. */
  protected readonly highlightMonthIndex = computed(() => Math.max(0, this.chartBars().length - 1));

  private transactionToRow(tx: Transaction, cmap: Map<string, Category>): TimelineRow {
    const cat = tx.category ? cmap.get(tx.category) : undefined;
    const key = calendarDateKey(tx);
    const [, m, d] = key.split('-').map(Number);
    const dateLabel = `${MONTH_SHORT[m - 1]} ${pad2(d)}`.toUpperCase();
    const isSubscription = tx.matched_recurring_pattern != null;
    return {
      id: tx.id,
      dateLabel,
      title: tx.description,
      subtitle: isSubscription ? 'Online Subscription' : '',
      amount: Number(tx.amount),
      currency: tx.currency,
      isSubscription,
      categoryLabel: cat?.name ?? 'Uncategorized',
      categoryColor: cat?.color ?? '#94a3b8',
      direction: tx.direction,
    };
  }

  protected formatVsLastMonthLabel(pct: number): string {
    const sign = pct > 0 ? '+' : '';
    return `${sign}${pct.toFixed(1)}%`;
  }

  protected formatUsd(amount: number, fractionDigits = 2): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
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

  /** Same visual recipe as transactions `categoryStyles`. */
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
    this.transactionService
      .getRecurringPatterns()
      .subscribe((pats) => this.recurringPatterns.set(pats));
  }

  protected onVisaImportReviewCompleted(): void {
    this.toast.success('Statement imported');
  }

  private loadTimeline(): void {
    this.viTimelineSub?.unsubscribe();
    this.timelineLoading.set(true);
    this.timelineError.set(null);
    this.viTimelineSub = this.transactionService
      .getVisaInternationalDashboard(this.selectedYear(), this.selectedMonth())
      .subscribe({
        next: (body) => {
          this.currentStatement.set(body.statement);
          this.transactions.set(body.transactions);
          this.monthlyTotals.set(body.monthly_totals);
          this.timelineLoading.set(false);
        },
        error: () => {
          this.timelineLoading.set(false);
          const msg = 'Could not load Visa International dashboard.';
          this.timelineError.set(msg);
          this.toast.error(msg);
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
    this.editServerError.set(null);
    const t = this.transactions().find((x) => x.id === row.id);
    if (t) {
      this.editTarget.set(t);
    }
  }

  protected onEditDismissed(): void {
    this.editTarget.set(null);
  }

  protected onEditSaveRequest(event: { id: string; payload: UpdateTransactionPayload }): void {
    this.editSaving.set(true);
    this.editServerError.set(null);
    this.transactionService
      .updateTransaction(event.id, event.payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.editSaving.set(false);
          this.editTarget.set(null);
          this.toast.success('Changes saved');
          this.loadTimeline();
          this.transactionService
            .getRecurringPatterns()
            .subscribe((pats) => this.recurringPatterns.set(pats));
        },
        error: (err: unknown) => {
          this.editSaving.set(false);
          this.editServerError.set(httpErrorMessage(err) ?? 'Could not update transaction.');
        },
      });
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
    this.toast.success('Recurring pattern saved');
    this.loadTimeline();
    this.transactionService
      .getRecurringPatterns()
      .subscribe((pats) => this.recurringPatterns.set(pats));
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
