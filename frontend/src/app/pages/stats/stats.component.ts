import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  OnDestroy,
  Injector,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Chart } from 'chart.js/auto';

import { CategoryTrendDialogComponent } from '../../components/category-trend-dialog/category-trend-dialog.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { StatsCategoryItem } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

const NOW = new Date();
const CURRENT_YEAR = NOW.getFullYear();
const CURRENT_MONTH = NOW.getMonth() + 1;

function buildYearOptions(): number[] {
  const years: number[] = [];
  for (let y = CURRENT_YEAR; y >= CURRENT_YEAR - 5; y--) {
    years.push(y);
  }
  return years;
}

const MONTH_LABELS = [
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
];

@Component({
  selector: 'app-stats',
  standalone: true,
  imports: [CommonModule, SidebarComponent, TopNavComponent, CategoryTrendDialogComponent],
  templateUrl: './stats.component.html',
  styleUrl: './stats.component.scss',
})
export class StatsComponent implements OnDestroy {
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);

  readonly pieCanvas = viewChild<ElementRef<HTMLCanvasElement>>('pieCanvas');

  protected readonly yearOptions = buildYearOptions();
  protected readonly monthOptions = MONTH_LABELS.map((label, i) => ({ value: i + 1, label }));

  protected readonly selectedYear = signal(CURRENT_YEAR);
  protected readonly selectedMonth = signal(CURRENT_MONTH);

  protected readonly categories = signal<StatsCategoryItem[]>([]);
  protected readonly monthTotal = signal<string>('0.00');
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly showTrend = signal(false);
  protected readonly trendCategory = signal<StatsCategoryItem | null>(null);

  private pieChart: Chart | null = null;
  private loadSeq = 0;

  constructor() {
    this.loadData();
  }

  ngOnDestroy(): void {
    this.destroyPie();
  }

  private loadData(): void {
    const seq = ++this.loadSeq;
    this.isLoading.set(true);
    this.loadError.set(null);
    this.transactionService
      .getStatsMonthly(this.selectedMonth(), this.selectedYear())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          if (seq !== this.loadSeq) {
            return;
          }
          this.categories.set(resp.categories);
          this.monthTotal.set(resp.total);
          this.isLoading.set(false);
          if (!resp.categories.length) {
            this.destroyPie();
            return;
          }
          afterNextRender(() => this.renderPie(), { injector: this.injector });
        },
        error: () => {
          if (seq !== this.loadSeq) {
            return;
          }
          this.loadError.set('Could not load stats. Please try again.');
          this.isLoading.set(false);
          this.categories.set([]);
          this.destroyPie();
        },
      });
  }

  protected onMonthChange(event: Event): void {
    const v = parseInt((event.target as HTMLSelectElement).value, 10);
    if (!isNaN(v)) {
      this.selectedMonth.set(v);
      this.loadData();
    }
  }

  protected onYearChange(event: Event): void {
    const v = parseInt((event.target as HTMLSelectElement).value, 10);
    if (!isNaN(v)) {
      this.selectedYear.set(v);
      this.loadData();
    }
  }

  protected openTrend(cat: StatsCategoryItem): void {
    this.trendCategory.set(cat);
    this.showTrend.set(true);
  }

  protected onTrendDismissed(): void {
    this.showTrend.set(false);
    this.trendCategory.set(null);
  }

  protected formatAmount(raw: string): string {
    const n = parseFloat(raw);
    if (isNaN(n)) return raw;
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  }

  protected formatPercent(p: number): string {
    return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(p)}%`;
  }

  private destroyPie(): void {
    if (this.pieChart) {
      this.pieChart.destroy();
      this.pieChart = null;
    }
  }

  private renderPie(): void {
    const cats = this.categories();
    const canvas = this.pieCanvas()?.nativeElement;
    if (!canvas) {
      return;
    }

    this.destroyPie();

    if (!cats.length) {
      return;
    }

    const labels = cats.map((c) => c.name);
    const data = cats.map((c) => parseFloat(c.amount));
    const colors = cats.map((c) => c.color ?? '#6750a4');

    const formatAmount = (raw: string) => this.formatAmount(raw);
    const formatPct = (p: number) => this.formatPercent(p);

    this.pieChart = new Chart(canvas, {
      type: 'pie',
      data: {
        labels,
        datasets: [
          {
            data,
            backgroundColor: colors,
            borderWidth: 1,
            borderColor: '#ffffff',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.raw as number;
                const pct = cats[ctx.dataIndex]?.percentage;
                const pctStr = pct != null ? formatPct(pct) : '';
                const label = ctx.label ?? '';
                return `${label}: ${formatAmount(String(v))} (${pctStr})`;
              },
            },
          },
        },
      },
    });
  }
}
