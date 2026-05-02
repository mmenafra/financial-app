import { CommonModule } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { HistoricCategoryModalComponent } from '../../components/historic-category-modal/historic-category-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { HistoricCategoryData } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';

const STORAGE_KEY = 'historic_selected_category_ids';
const CURRENT_YEAR = new Date().getFullYear();

function buildYearOptions(): number[] {
  const years: number[] = [];
  for (let y = CURRENT_YEAR; y >= CURRENT_YEAR - 5; y--) {
    years.push(y);
  }
  return years;
}

function loadPersistedIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'string')) {
      return parsed as string[];
    }
  } catch {
    // ignore corrupt data
  }
  return [];
}

function persistIds(ids: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // ignore storage errors
  }
}

@Component({
  selector: 'app-historic',
  standalone: true,
  imports: [CommonModule, SidebarComponent, TopNavComponent, HistoricCategoryModalComponent],
  templateUrl: './historic.component.html',
  styleUrl: './historic.component.scss',
})
export class HistoricComponent {
  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly yearOptions = buildYearOptions();
  protected readonly selectedYear = signal(CURRENT_YEAR);
  protected readonly selectedIds = signal<string[]>(loadPersistedIds());
  protected readonly showModal = signal(false);

  protected readonly months = signal<string[]>([]);
  protected readonly categories = signal<HistoricCategoryData[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly columnTotals = computed(() => {
    const cats = this.categories();
    const mons = this.months();
    return cats.map((cat) => {
      let total = 0;
      for (const m of mons) {
        total += parseFloat(cat.monthly_totals[m] ?? '0');
      }
      return total;
    });
  });

  protected readonly rowTotals = computed(() => {
    const cats = this.categories();
    return this.months().map((m) =>
      cats.reduce((sum, cat) => sum + parseFloat(cat.monthly_totals[m] ?? '0'), 0),
    );
  });

  protected readonly grandTotal = computed(() => this.rowTotals().reduce((sum, t) => sum + t, 0));

  constructor() {
    this.loadData();
  }

  private loadData(): void {
    const ids = this.selectedIds();
    if (!ids.length) {
      this.months.set([]);
      this.categories.set([]);
      return;
    }
    this.isLoading.set(true);
    this.loadError.set(null);
    this.transactionService
      .getHistoric(ids, this.selectedYear())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.months.set(resp.months);
          this.categories.set(resp.categories);
          this.isLoading.set(false);
        },
        error: () => {
          this.loadError.set('Could not load historic data. Please try again.');
          this.isLoading.set(false);
        },
      });
  }

  protected onYearChange(event: Event): void {
    const year = parseInt((event.target as HTMLSelectElement).value, 10);
    if (!isNaN(year)) {
      this.selectedYear.set(year);
      this.loadData();
    }
  }

  protected openModal(): void {
    this.showModal.set(true);
  }

  protected onModalDismissed(): void {
    this.showModal.set(false);
  }

  protected onModalConfirmed(ids: string[]): void {
    this.showModal.set(false);
    this.selectedIds.set(ids);
    persistIds(ids);
    this.loadData();
  }

  protected formatMonth(key: string): string {
    const [yearStr, monthStr] = key.split('-');
    const year = parseInt(yearStr, 10);
    const month = parseInt(monthStr, 10);
    if (isNaN(year) || isNaN(month)) return key;
    const date = new Date(year, month - 1, 1);
    return date.toLocaleDateString(undefined, { month: 'short' });
  }

  protected formatAmount(value: number): string {
    if (value === 0) return '—';
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }

  protected formatCellAmount(raw: string): string {
    const n = parseFloat(raw);
    return this.formatAmount(n);
  }
}
