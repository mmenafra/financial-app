import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  OnDestroy,
  inject,
  Injector,
  afterNextRender,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { Chart } from 'chart.js/auto';
import { combineLatest, finalize, switchMap } from 'rxjs';

import type { StatsCategoryItem, StatsTrendResponse } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

@Component({
  selector: 'app-category-trend-dialog',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './category-trend-dialog.component.html',
  styleUrl: './category-trend-dialog.component.scss',
})
export class CategoryTrendDialogComponent implements OnDestroy {
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);

  readonly lineCanvas = viewChild<ElementRef<HTMLCanvasElement>>('lineCanvas');

  readonly category = input.required<StatsCategoryItem>();
  readonly referenceMonth = input.required<number>();
  readonly referenceYear = input.required<number>();
  readonly dismissed = output<void>();

  protected readonly data = signal<StatsTrendResponse | null>(null);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  private chart: Chart | null = null;

  constructor() {
    combineLatest([
      toObservable(this.category),
      toObservable(this.referenceMonth),
      toObservable(this.referenceYear),
    ])
      .pipe(
        switchMap(([cat, m, y]) => {
          this.isLoading.set(true);
          this.loadError.set(null);
          return this.transactionService
            .getStatsTrend(cat.id, m, y)
            .pipe(finalize(() => this.isLoading.set(false)));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.data.set(resp);
          afterNextRender(() => this.renderChart(), { injector: this.injector });
        },
        error: () => {
          this.data.set(null);
          this.loadError.set('Could not load trend. Please try again.');
        },
      });
  }

  ngOnDestroy(): void {
    this.destroyChart();
  }

  protected onBackdrop(): void {
    this.dismissed.emit();
  }

  protected formatMonthKey(key: string): string {
    const [y, m] = key.split('-');
    const year = parseInt(y, 10);
    const month = parseInt(m, 10);
    if (isNaN(year) || isNaN(month)) return key;
    return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
      month: 'short',
      year: 'numeric',
    });
  }

  private destroyChart(): void {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
  }

  private renderChart(): void {
    const resp = this.data();
    const canvas = this.lineCanvas()?.nativeElement;
    if (!resp || !canvas) {
      return;
    }

    const labels = resp.months.map((k) => this.formatMonthKey(k));
    const values = resp.totals.map((t) => parseFloat(t));

    const color = resp.category.color ?? '#6750a4';

    this.destroyChart();
    this.chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: resp.category.name,
            data: values,
            borderColor: color,
            backgroundColor: `${color}33`,
            fill: true,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) =>
                typeof value === 'number'
                  ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value)
                  : value,
            },
          },
        },
      },
    });
  }
}
