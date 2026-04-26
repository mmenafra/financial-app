import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { Category } from '../../models/transaction.model';
import { CategoryService, type CategoryWrite } from '../../services/category.service';

const DEFAULT_FORM_COLOR = '#6366f1';

@Component({
  selector: 'app-categories',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, SidebarComponent, TopNavComponent],
  templateUrl: './categories.component.html',
  styleUrl: './categories.component.scss',
})
export class CategoriesComponent {
  private readonly categoryService = inject(CategoryService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly form = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    icon: ['', [Validators.maxLength(50)]],
    color: [DEFAULT_FORM_COLOR],
    parent: [null as string | null],
  });

  protected readonly categories = signal<Category[]>([]);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly formModalOpen = signal(false);
  protected readonly formSubmitting = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly deleteModalOpen = signal(false);
  protected readonly deleteSubmitting = signal(false);
  protected readonly loadDeleteError = signal<string | null>(null);
  protected readonly openMenuId = signal<string | null>(null);
  protected readonly editingId = signal<string | null>(null);
  protected readonly pendingDelete = signal<Category | null>(null);

  protected readonly categoryById = computed(() => {
    const map = new Map<string, Category>();
    for (const c of this.categories()) {
      map.set(c.id, c);
    }
    return map;
  });

  protected readonly parentOptions = computed(() => {
    const editing = this.editingId();
    const list = this.categories();
    if (!editing) {
      return list;
    }
    return list.filter((c) => c.id !== editing);
  });

  protected readonly isEditMode = computed(() => this.editingId() !== null);

  constructor() {
    this.reload();
  }

  protected reload(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.categoryService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => {
          this.categories.set(rows);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.loadError.set(this.httpErrorMessage(err) ?? 'Could not load categories.');
        },
      });
  }

  protected openAddModal(): void {
    this.openMenuId.set(null);
    this.editingId.set(null);
    this.formError.set(null);
    this.form.reset({
      name: '',
      icon: '',
      color: DEFAULT_FORM_COLOR,
      parent: null,
    });
    this.formModalOpen.set(true);
  }

  protected openEditModal(c: Category, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.editingId.set(c.id);
    this.formError.set(null);
    this.form.setValue({
      name: c.name,
      icon: c.icon ?? '',
      color: c.color && /^#[0-9A-Fa-f]{6}$/.test(c.color) ? c.color : DEFAULT_FORM_COLOR,
      parent: c.parent,
    });
    this.formModalOpen.set(true);
  }

  protected closeFormModal(): void {
    this.formModalOpen.set(false);
    this.editingId.set(null);
    this.formError.set(null);
  }

  protected saveCategory(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.formError.set(null);
    const raw = this.form.getRawValue();
    const name = (raw.name ?? '').trim();
    if (!name) {
      this.formError.set('Name is required.');
      return;
    }
    const iconVal = (raw.icon ?? '').trim();
    const hex = (raw.color as string) ?? DEFAULT_FORM_COLOR;
    const body: CategoryWrite = {
      name,
      parent: raw.parent || null,
      icon: iconVal || null,
      color: hex || null,
    };

    const id = this.editingId();
    this.formSubmitting.set(true);
    const req$ = id
      ? this.categoryService.updateCategory(id, body)
      : this.categoryService.createCategory(body);

    req$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.formSubmitting.set(false);
        this.closeFormModal();
        this.reload();
      },
      error: (err: unknown) => {
        this.formSubmitting.set(false);
        this.formError.set(this.httpErrorMessage(err) ?? 'Could not save category.');
      },
    });
  }

  protected openDeleteModal(c: Category, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.loadDeleteError.set(null);
    this.pendingDelete.set(c);
    this.deleteModalOpen.set(true);
  }

  protected closeDeleteModal(): void {
    this.deleteModalOpen.set(false);
    this.pendingDelete.set(null);
    this.loadDeleteError.set(null);
  }

  protected confirmDelete(): void {
    const c = this.pendingDelete();
    if (!c) {
      return;
    }
    this.loadDeleteError.set(null);
    this.deleteSubmitting.set(true);
    this.categoryService
      .deleteCategory(c.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.deleteSubmitting.set(false);
          this.closeDeleteModal();
          this.reload();
        },
        error: (err: unknown) => {
          this.deleteSubmitting.set(false);
          this.loadDeleteError.set(
            this.httpErrorMessage(err) ?? 'Could not delete category.',
          );
        },
      });
  }

  @HostListener('document:click')
  protected closeMenu(): void {
    this.openMenuId.set(null);
  }

  protected toggleMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected parentName(parentId: string | null | undefined): string {
    if (!parentId) {
      return '—';
    }
    return this.categoryById().get(parentId)?.name ?? '—';
  }

  private httpErrorMessage(err: unknown): string | null {
    if (err && typeof err === 'object' && 'error' in err) {
      const e = (err as { error?: unknown }).error;
      if (typeof e === 'string' && e) {
        return e;
      }
      if (e && typeof e === 'object' && 'detail' in e) {
        const d = (e as { detail?: string }).detail;
        if (typeof d === 'string') {
          return d;
        }
      }
    }
    return null;
  }
}
