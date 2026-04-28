import { CommonModule } from '@angular/common';
import {
  Component,
  ElementRef,
  HostListener,
  Injector,
  Input,
  afterNextRender,
  computed,
  forwardRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

import type { Category } from '../../models/transaction.model';

@Component({
  selector: 'app-category-select',
  standalone: true,
  imports: [CommonModule],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => CategorySelectComponent),
      multi: true,
    },
  ],
  templateUrl: './category-select.component.html',
})
export class CategorySelectComponent implements ControlValueAccessor {
  @Input() categories: Category[] = [];

  private readonly injector = inject(Injector);
  private readonly searchInput = viewChild<ElementRef<HTMLInputElement>>('categorySearchInput');

  protected readonly isOpen = signal(false);
  protected readonly searchText = signal('');
  protected readonly selectedId = signal<string | null>(null);
  protected readonly isDisabled = signal(false);

  private onChange: (value: string | null) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(private readonly el: ElementRef) {}

  protected readonly filtered = computed(() => {
    const q = this.searchText().toLowerCase().trim();
    if (!q) return this.categories;
    return this.categories.filter((c) => c.name.toLowerCase().includes(q));
  });

  protected readonly selectedLabel = computed(() => {
    const id = this.selectedId();
    if (!id) return 'Uncategorized';
    return this.categories.find((c) => c.id === id)?.name ?? 'Uncategorized';
  });

  protected readonly selectedColor = computed(() => {
    const id = this.selectedId();
    if (!id) return null;
    return this.categories.find((c) => c.id === id)?.color ?? null;
  });

  writeValue(value: string | null): void {
    this.selectedId.set(value ?? null);
  }

  registerOnChange(fn: (value: string | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.isDisabled.set(isDisabled);
  }

  protected open(): void {
    if (this.isDisabled()) return;
    this.searchText.set('');
    this.isOpen.set(true);
    this.onTouched();
    afterNextRender(
      () => {
        this.searchInput()?.nativeElement?.focus();
      },
      { injector: this.injector },
    );
  }

  protected select(id: string | null): void {
    this.selectedId.set(id);
    this.onChange(id);
    this.isOpen.set(false);
    this.searchText.set('');
  }

  protected onSearchInput(event: Event): void {
    this.searchText.set((event.target as HTMLInputElement).value);
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.el.nativeElement.contains(event.target as Node)) {
      this.isOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.isOpen.set(false);
  }
}
