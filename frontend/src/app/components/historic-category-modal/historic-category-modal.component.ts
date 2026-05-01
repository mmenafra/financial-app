import { CommonModule } from '@angular/common';
import { Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import type { Category } from '../../models/transaction.model';
import { CategoryService } from '../../services/category.service';

@Component({
  selector: 'app-historic-category-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historic-category-modal.component.html',
  styleUrl: './historic-category-modal.component.scss',
})
export class HistoricCategoryModalComponent {
  private readonly categoryService = inject(CategoryService);
  private readonly destroyRef = inject(DestroyRef);

  /** Currently selected category IDs (passed in so we can pre-check them). */
  readonly selectedIds = input<string[]>([]);

  readonly confirmed = output<string[]>();
  readonly dismissed = output<void>();

  protected readonly allCategories = signal<Category[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly searchQuery = signal('');

  protected pendingIds = new Set<string>();

  constructor() {
    this.isLoading.set(true);
    this.categoryService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (cats) => {
          this.allCategories.set(cats);
          this.pendingIds = new Set(this.selectedIds());
          this.isLoading.set(false);
        },
        error: () => {
          this.loadError.set('Could not load categories.');
          this.isLoading.set(false);
        },
      });
  }

  protected get filteredCategories(): Category[] {
    const q = this.searchQuery().toLowerCase().trim();
    const all = this.allCategories();
    if (!q) return all;
    return all.filter((c) => c.name.toLowerCase().includes(q));
  }

  protected toggle(id: string): void {
    if (this.pendingIds.has(id)) {
      this.pendingIds.delete(id);
    } else {
      this.pendingIds.add(id);
    }
  }

  protected isChecked(id: string): boolean {
    return this.pendingIds.has(id);
  }

  protected confirm(): void {
    this.confirmed.emit([...this.pendingIds]);
  }

  protected onBackdrop(): void {
    this.dismissed.emit();
  }
}
