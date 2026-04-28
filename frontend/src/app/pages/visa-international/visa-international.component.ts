import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ImportModalComponent } from '../../components/import-modal/import-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { Category } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

type TimelineKind = 'subscription' | 'installment' | 'other';
type TimelineTab = 'all' | 'subscriptions' | 'installments';

interface TimelineRow {
  id: string;
  dateLabel: string;
  title: string;
  subtitle: string;
  /** Amount in major units (e.g. 19.99). */
  amount: number;
  /** ISO 4217 currency code. */
  currency: string;
  kind: TimelineKind;
  /** Display label for category pill (mock until API). */
  categoryLabel: string;
  /** Hex color for category pill, e.g. #6366f1 */
  categoryColor: string;
}

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

/** Bar chart mock series (USD, Jan–Dec). Replace when API is wired. */
const BAR_CHART_MOCK_SERIES: readonly number[] = [
  7120, 6890, 8450, 7980, 9120, 8760, 9340, 8010, 8880, 12450, 9020, 9680,
];

@Component({
  selector: 'app-visa-international',
  standalone: true,
  imports: [CommonModule, ImportModalComponent, SidebarComponent, TopNavComponent],
  templateUrl: './visa-international.component.html',
  styleUrl: './visa-international.component.scss',
})
export class VisaInternationalComponent {
  private readonly destroyRef = inject(DestroyRef);
  private readonly transactionService = inject(TransactionService);

  constructor() {
    this.transactionService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((cats) => this.categories.set(cats));
  }

  protected readonly categories = signal<Category[]>([]);
  protected readonly importModalOpen = signal(false);
  protected readonly importVisaInternationalSubmit = (file: File) =>
    this.transactionService.importVisaInternational(file);

  protected readonly monthShort = MONTH_SHORT;

  protected readonly selectedYear = signal(new Date().getFullYear());
  protected readonly selectedMonth = signal(new Date().getMonth() + 1);

  protected readonly timelineTab = signal<TimelineTab>('all');
  protected readonly openMenuId = signal<string | null>(null);

  /** Mock headline liquidity (display only). */
  protected readonly forecastAmountUsd = 12450.0;
  protected readonly vsLastMonthPct = 4.2;

  protected readonly barChartMockSeries = BAR_CHART_MOCK_SERIES;

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

  protected readonly mockTimeline: TimelineRow[] = [
    {
      id: 'vi-timeline-1',
      dateLabel: 'OCT 12',
      title: 'Netflix Premium',
      subtitle: 'Monthly Streaming Service',
      amount: 19.99,
      currency: 'USD',
      kind: 'subscription',
      categoryLabel: 'Entertainment',
      categoryColor: '#7c3aed',
    },
    {
      id: 'vi-timeline-2',
      dateLabel: 'OCT 14',
      title: 'Apple MacBook Pro',
      subtitle: 'Installment 6 of 12',
      amount: 249,
      currency: 'USD',
      kind: 'installment',
      categoryLabel: 'Electronics',
      categoryColor: '#0891b2',
    },
    {
      id: 'vi-timeline-3',
      dateLabel: 'OCT 18',
      title: 'Spotify Family',
      subtitle: 'Monthly Streaming Service',
      amount: 14.99,
      currency: 'EUR',
      kind: 'subscription',
      categoryLabel: 'Entertainment',
      categoryColor: '#7c3aed',
    },
    {
      id: 'vi-timeline-4',
      dateLabel: 'OCT 28',
      title: 'Mortgage Repayment',
      subtitle: 'Scheduled debit',
      amount: 1850,
      currency: 'USD',
      kind: 'other',
      categoryLabel: 'Housing',
      categoryColor: '#0d9488',
    },
  ];

  protected readonly barMax = computed(() =>
    Math.max(1, ...this.barChartMockSeries.map((v) => Number(v))),
  );

  protected readonly chartAriaLabel = computed(() => {
    const y = this.selectedYear();
    return `Monthly liquidity by calendar month for ${y}. Values shown are placeholders until live data is available.`;
  });

  protected readonly periodRangeLabel = computed(() => {
    const y = this.selectedYear();
    const m = this.selectedMonth();
    const pad = (n: number) => String(n).padStart(2, '0');
    const lastDay = new Date(y, m, 0).getDate();
    const mon = MONTH_SHORT[m - 1].toUpperCase();
    return `CURRENT PERIOD: ${mon} 01 - ${mon} ${pad(lastDay)}`;
  });

  protected readonly filteredTimeline = computed(() => {
    const tab = this.timelineTab();
    const rows = this.mockTimeline;
    if (tab === 'all') {
      return rows;
    }
    if (tab === 'subscriptions') {
      return rows.filter((r) => r.kind === 'subscription');
    }
    return rows.filter((r) => r.kind === 'installment');
  });

  protected readonly highlightMonthIndex = computed(() => this.selectedMonth() - 1);

  protected barHeightPercent(value: number): number {
    return (value / this.barMax()) * 100;
  }

  /** Mock bar chart values are USD liquidity (major units). */
  protected formatChartBarValue(value: number): string {
    return this.formatUsd(value);
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
    }
  }

  protected onYearChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    if (!Number.isNaN(v)) {
      this.selectedYear.set(v);
    }
  }

  protected setTimelineTab(tab: TimelineTab): void {
    this.timelineTab.set(tab);
  }

  /** Stub until import flow exists for Visa International. */
  protected openImportModal(): void {
    this.importModalOpen.set(true);
  }

  protected closeImportModal(): void {
    this.importModalOpen.set(false);
  }

  /** Future: refresh Visa International timeline from API after import completes. */
  protected onVisaImportDone(): void {
    //
  }


  @HostListener('document:click')
  protected closeMenus(): void {
    this.openMenuId.set(null);
  }

  protected toggleTimelineMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected onEditRow(_row: TimelineRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
  }

  protected onMetaDataRow(_row: TimelineRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
  }
}
