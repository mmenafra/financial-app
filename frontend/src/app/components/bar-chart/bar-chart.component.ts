import {
  AfterViewInit,
  Component,
  Input,
  OnChanges,
  OnDestroy,
  viewChild,
  ElementRef,
} from '@angular/core';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  Tooltip,
  type ChartConfiguration,
} from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

/** Project palette tokens mirrored from tailwind.config.js. */
const BAR_DEFAULT = '#79f7e3cc'; // secondary-fixed ~80% opacity
const BAR_CURRENT = '#006b5f'; // secondary
const TICK_COLOR = '#44474e'; // on-surface-variant
const GRID_COLOR = '#c4c6cf40'; // outline-variant ~25% opacity

@Component({
  selector: 'app-bar-chart',
  standalone: true,
  template: `<canvas #canvasRef></canvas>`,
  styles: [
    `
      :host {
        display: block;
        height: 100%;
        width: 100%;
      }
      canvas {
        display: block;
        width: 100% !important;
        height: 100% !important;
      }
    `,
  ],
})
export class BarChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() labels: string[] = [];
  @Input() data: number[] = [];
  /** Index of the bar to highlight (current period). -1 = none. */
  @Input() highlightIndex = -1;
  /** Tooltip value formatter; defaults to plain string conversion. */
  @Input() formatValue: (v: number) => string = String;

  private readonly canvasRef = viewChild<ElementRef<HTMLCanvasElement>>('canvasRef');
  private chart: Chart<'bar'> | null = null;

  ngAfterViewInit(): void {
    this.buildChart();
  }

  ngOnChanges(): void {
    if (this.chart) {
      this.syncChart();
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
    this.chart = null;
  }

  private barColors(): string[] {
    return this.data.map((_, i) => (i === this.highlightIndex ? BAR_CURRENT : BAR_DEFAULT));
  }

  private buildChart(): void {
    const el = this.canvasRef()?.nativeElement;
    if (!el) return;

    const config: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels: this.labels,
        datasets: [
          {
            data: this.data,
            backgroundColor: this.barColors(),
            borderRadius: 6,
            borderSkipped: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ' ' + this.formatValue(ctx.parsed.y ?? 0),
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              font: { size: 10, weight: 'bold' },
              color: TICK_COLOR,
              maxRotation: 0,
            },
          },
          y: {
            grid: { color: GRID_COLOR },
            border: { display: false },
            ticks: { display: false },
          },
        },
      },
    };

    this.chart = new Chart(el, config);
  }

  private syncChart(): void {
    if (!this.chart) return;
    this.chart.data.labels = this.labels;
    this.chart.data.datasets[0].data = this.data;
    (this.chart.data.datasets[0] as unknown as { backgroundColor: string[] }).backgroundColor =
      this.barColors();
    this.chart.update('none');
  }
}
