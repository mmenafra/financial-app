import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ImportModalComponent } from '../../components/import-modal/import-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import type { FileImportRow } from '../../models/file-import.model';
import type { BankStatementImportResult, Category, Source } from '../../models/transaction.model';
import { FileImportService } from '../../services/file-import.service';
import { ToastService } from '../../services/toast.service';
import { TransactionService } from '../../services/transaction.service';
import { presetsForImportSource } from '../../utils/import-modal-source-presets';
import { normalizeBankStatementImportResult } from '../../utils/normalize-bank-statement-import-result';
import { resolveApiFileUrl } from '../../utils/resolve-api-file-url';

const PAGE_SIZE = 20;

const SOURCE_LABELS: Record<Source, string> = {
  MERCADOPAGO: 'Mercado Pago',
  BANK_ACCOUNT: 'Bank account',
  CREDIT_CARD_NATIONAL: 'Credit card (national)',
  CREDIT_CARD_INTERNATIONAL: 'Credit card (international)',
};

@Component({
  selector: 'app-imports',
  standalone: true,
  imports: [CommonModule, ImportModalComponent, SidebarComponent, TopNavComponent],
  templateUrl: './imports.component.html',
  styleUrl: './imports.component.scss',
})
export class ImportsComponent {
  private readonly fileImportService = inject(FileImportService);
  private readonly transactionService = inject(TransactionService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly pageSize = PAGE_SIZE;
  protected readonly currentPage = signal(1);
  protected readonly rows = signal<FileImportRow[]>([]);
  protected readonly totalCount = signal(0);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly openMenuId = signal<string | null>(null);
  protected readonly rerunSubmittingId = signal<string | null>(null);

  protected readonly categories = signal<Category[]>([]);
  protected readonly rerunResultModalOpen = signal(false);
  /** Set when POST re-run succeeds; drives source-specific modal copy via `rerunModalPreset`. */
  protected readonly rerunModalSource = signal<Source>('BANK_ACCOUNT');
  protected readonly prefilledImportResult = signal<BankStatementImportResult | null>(null);

  protected readonly rerunModalPreset = computed(() =>
    presetsForImportSource(this.rerunModalSource()),
  );

  constructor() {
    this.transactionService
      .getCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (cats) => this.categories.set(cats),
        error: () => {
          // Category list enhances re-run modal; imports table still usable without it.
        },
      });
    this.reload();
  }

  protected reload(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    this.fileImportService
      .list(this.currentPage(), PAGE_SIZE)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page) => {
          this.rows.set(page.results);
          this.totalCount.set(page.count);
          this.isLoading.set(false);
        },
        error: () => {
          this.loadError.set('Could not load imports. Try again.');
          this.isLoading.set(false);
        },
      });
  }

  protected closeRerunModal(): void {
    this.rerunResultModalOpen.set(false);
    this.prefilledImportResult.set(null);
  }

  protected onRerunImportReviewCompleted(): void {
    this.toast.success('Import complete');
  }

  /** Link target for uploaded PDF/files (same origin as API when using root-relative URLs). */
  protected fileDownloadHref(raw: FileImportRow['file']): string | null {
    return resolveApiFileUrl(raw ?? null);
  }

  protected formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  protected sourceLabel(source: Source): string {
    return SOURCE_LABELS[source] ?? source;
  }

  protected statusClass(status: FileImportRow['status']): string {
    switch (status) {
      case 'COMPLETED':
        return 'text-green-700 font-semibold';
      case 'FAILED':
        return 'text-red-600 font-semibold';
      case 'PROCESSING':
      case 'PENDING':
        return 'text-on-surface-variant font-semibold';
      default:
        return 'font-semibold text-on-surface';
    }
  }

  protected totalPages(): number {
    return Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
  }

  protected showingFrom(): number {
    const count = this.totalCount();
    if (count === 0) {
      return 0;
    }
    return (this.currentPage() - 1) * PAGE_SIZE + 1;
  }

  protected showingTo(): number {
    return Math.min(this.currentPage() * PAGE_SIZE, this.totalCount());
  }

  protected pageNumbers(): (number | 'ellipsis')[] {
    const totalPages = this.totalPages();
    const cur = this.currentPage();
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages = new Set<number>();
    pages.add(1);
    pages.add(totalPages);
    for (let i = cur - 1; i <= cur + 1; i++) {
      if (i >= 1 && i <= totalPages) {
        pages.add(i);
      }
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const out: (number | 'ellipsis')[] = [];
    for (let i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
        out.push('ellipsis');
      }
      out.push(sorted[i]);
    }
    return out;
  }

  protected goToPage(p: number): void {
    const totalPages = Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
    const next = Math.min(Math.max(1, p), totalPages);
    this.currentPage.set(next);
    this.reload();
  }

  @HostListener('document:click')
  protected closeMenu(): void {
    this.openMenuId.set(null);
  }

  protected toggleMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected rerun(row: FileImportRow, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.rerunSubmittingId.set(row.id);
    this.fileImportService
      .rerun(row.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.rerunSubmittingId.set(null);
          this.loadError.set(null);
          const payload = response.import_result;
          if (payload != null && typeof payload === 'object') {
            this.rerunModalSource.set(row.source);
            this.prefilledImportResult.set(
              normalizeBankStatementImportResult(payload as BankStatementImportResult),
            );
            this.rerunResultModalOpen.set(true);
            return;
          }
          this.reload();
        },
        error: () => {
          this.rerunSubmittingId.set(null);
          const msg = 'Re-run failed. Try again.';
          this.loadError.set(msg);
          this.toast.error(msg);
        },
      });
  }
}
