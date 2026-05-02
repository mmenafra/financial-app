import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, effect, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { Actions, ofType } from '@ngrx/effects';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Store } from '@ngrx/store';

import { CategorySelectComponent } from '../../components/category-select/category-select.component';
import { ImportModalComponent } from '../../components/import-modal/import-modal.component';
import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import { TransactionEditModalComponent } from '../../components/transaction-edit-modal/transaction-edit-modal.component';
import { TransactionMetadataModalComponent } from '../../components/transaction-metadata-modal/transaction-metadata-modal.component';
import type {
  Category,
  CreateTransactionPayload,
  Direction,
  Source,
  Transaction,
  TransactionType,
  UpdateTransactionPayload,
} from '../../models/transaction.model';
import { ToastService } from '../../services/toast.service';
import { TransactionService } from '../../services/transaction.service';
import { TransactionsPageActions } from '../../store/transactions-page/transactions-page.actions';
import { transactionsPageFeature } from '../../store/transactions-page/transactions-page.reducer';
import { selectSpendTotalsAndTrend } from '../../store/transactions-page/transactions-page.selectors';
import {
  transactionsPageInitialState,
  TRANSACTIONS_PAGE_SIZE,
} from '../../store/transactions-page/transactions-page.state';
import { positiveNumberValidator, round2 } from '../../utils/transaction-edit';

const PAGE_SIZE = TRANSACTIONS_PAGE_SIZE;
const CONNECTED_SOURCES = 4;

const SOURCE_LABELS: Record<Source, string> = {
  BANK_ACCOUNT: 'Bank Account',
  CREDIT_CARD_NATIONAL: 'Visa National',
  CREDIT_CARD_INTERNATIONAL: 'Visa International',
  MERCADOPAGO: 'MercadoPago',
};

@Component({
  selector: 'app-transactions',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    CategorySelectComponent,
    ImportModalComponent,
    SidebarComponent,
    TopNavComponent,
    TransactionEditModalComponent,
    TransactionMetadataModalComponent,
  ],
  templateUrl: './transactions.component.html',
  styleUrl: './transactions.component.scss',
})
export class TransactionsComponent {
  private readonly store = inject(Store);
  private readonly actions$ = inject(Actions);
  private readonly transactionService = inject(TransactionService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);

  private createSplitRow(): FormGroup {
    return this.fb.group({
      description: ['', [Validators.required, Validators.maxLength(255)]],
      amount: ['', [Validators.required]],
      category: [null as string | null],
    });
  }

  protected readonly pageSize = PAGE_SIZE;
  protected readonly connectedSources = CONNECTED_SOURCES;

  protected readonly selectedYear = toSignal(this.store.select(transactionsPageFeature.selectYear), {
    initialValue: transactionsPageInitialState.year,
  });
  protected readonly selectedMonth = toSignal(
    this.store.select(transactionsPageFeature.selectMonth),
    { initialValue: transactionsPageInitialState.month },
  );
  protected readonly currentPage = toSignal(this.store.select(transactionsPageFeature.selectPage), {
    initialValue: transactionsPageInitialState.page,
  });

  protected readonly categories = toSignal(
    this.store.select(transactionsPageFeature.selectCategories),
    { initialValue: transactionsPageInitialState.categories },
  );
  protected readonly transactions = toSignal(
    this.store.select(transactionsPageFeature.selectTransactions),
    { initialValue: transactionsPageInitialState.transactions },
  );
  protected readonly totalCount = toSignal(
    this.store.select(transactionsPageFeature.selectTotalCount),
    { initialValue: transactionsPageInitialState.totalCount },
  );
  protected readonly isLoading = toSignal(this.store.select(transactionsPageFeature.selectLoading), {
    initialValue: transactionsPageInitialState.loading,
  });
  protected readonly loadError = toSignal(
    this.store.select(transactionsPageFeature.selectLoadError),
    { initialValue: transactionsPageInitialState.loadError },
  );

  protected readonly filterCategoryId = toSignal(
    this.store.select(transactionsPageFeature.selectFilterCategoryId),
    { initialValue: transactionsPageInitialState.filterCategoryId },
  );
  protected readonly filterSource = toSignal(
    this.store.select(transactionsPageFeature.selectFilterSource),
    { initialValue: transactionsPageInitialState.filterSource },
  );

  protected readonly isUpdatingTransaction = toSignal(
    this.store.select(transactionsPageFeature.selectIsUpdatingTransaction),
    { initialValue: transactionsPageInitialState.isUpdatingTransaction },
  );
  protected readonly updateError = toSignal(
    this.store.select(transactionsPageFeature.selectUpdateError),
    { initialValue: transactionsPageInitialState.updateError },
  );

  protected readonly spendSummary = toSignal(this.store.select(selectSpendTotalsAndTrend), {
    initialValue: {
      rows: [] as { currency: string; amount: number }[],
      trendPct: null as number | null,
      trendSpentLess: null as boolean | null,
    },
  });
  protected readonly totalsByCurrency = computed(() => this.spendSummary().rows);
  protected readonly trendVsPrevMonthPct = computed(() => this.spendSummary().trendPct);
  protected readonly trendSpentLess = computed(() => this.spendSummary().trendSpentLess);

  protected readonly filterOpen = signal(false);
  protected readonly filterDraftCategory = signal<string | undefined>(undefined);
  protected readonly filterDraftSource = signal<Source | undefined>(undefined);

  protected readonly openMenuId = signal<string | null>(null);

  protected readonly splitModalOpen = signal(false);
  protected readonly splitSubmitting = signal(false);
  protected readonly splitError = signal<string | null>(null);
  protected readonly pendingSplit = signal<Transaction | null>(null);

  protected readonly splitForm = this.fb.group({
    rows: this.fb.array([this.createSplitRow(), this.createSplitRow()]),
  });

  protected readonly newTxModalOpen = signal(false);
  protected readonly newTxSubmitting = signal(false);
  protected readonly newTxError = signal<string | null>(null);

  protected readonly importModalOpen = signal(false);
  protected readonly importBankStatementSubmit = (file: File) =>
    this.transactionService.importBankStatement(file);

  protected readonly editTarget = signal<Transaction | null>(null);
  protected readonly metadataTarget = signal<Transaction | null>(null);

  protected readonly deleteModalOpen = signal(false);
  protected readonly deleteSubmitting = signal(false);
  protected readonly deleteError = signal<string | null>(null);
  protected readonly pendingDelete = signal<Transaction | null>(null);

  protected readonly newTxForm = this.fb.group({
    description: ['', [Validators.required, Validators.maxLength(255)]],
    amount: ['', [Validators.required, positiveNumberValidator]],
    currency: ['CLP', [Validators.required]],
    direction: ['EXPENSE', [Validators.required]],
    source: ['BANK_ACCOUNT', [Validators.required]],
    category: [null as string | null],
    date: [new Date().toISOString().slice(0, 10)],
  });

  protected readonly categoryById = computed(() => {
    const map = new Map<string, Category>();
    for (const c of this.categories()) {
      map.set(c.id, c);
    }
    return map;
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

  constructor() {
    const y = new Date().getFullYear();
    const m = new Date().getMonth() + 1;
    this.store.dispatch(TransactionsPageActions.initialized({ year: y, month: m }));

    effect(() => {
      if (this.filterOpen()) {
        this.filterDraftCategory.set(this.filterCategoryId());
        this.filterDraftSource.set(this.filterSource());
      }
    });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.deleteMutationSucceeded),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.deleteSubmitting.set(false);
        this.closeDeleteModal();
      });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.deleteMutationFailed),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ message }) => {
        this.deleteSubmitting.set(false);
        this.deleteError.set(message);
      });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.updateMutationSucceeded),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.editTarget.set(null);
      });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.createMutationSucceeded),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.newTxSubmitting.set(false);
        this.closeNewTxModal();
      });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.createMutationFailed),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ message }) => {
        this.newTxSubmitting.set(false);
        this.newTxError.set(message);
      });

    this.actions$
      .pipe(
        ofType(TransactionsPageActions.splitMutationSucceeded),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.splitSubmitting.set(false);
        this.closeSplitModal();
      });

    this.actions$
      .pipe(ofType(TransactionsPageActions.splitMutationFailed), takeUntilDestroyed(this.destroyRef))
      .subscribe(({ message }) => {
        this.splitSubmitting.set(false);
        this.splitError.set(message);
      });
  }

  protected onImportReviewCompleted(): void {
    this.toast.success('Import complete');
  }

  protected onImportListSync(): void {
    this.store.dispatch(TransactionsPageActions.importCompleted());
  }

  protected onYearChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    this.store.dispatch(TransactionsPageActions.yearChanged({ year: v }));
  }

  protected onMonthChange(event: Event): void {
    const v = Number((event.target as HTMLSelectElement).value);
    this.store.dispatch(TransactionsPageActions.monthChanged({ month: v }));
  }

  protected toggleFilters(): void {
    this.filterOpen.update((o) => !o);
  }

  protected onFilterDraftCategory(event: Event): void {
    const v = (event.target as HTMLSelectElement).value;
    this.filterDraftCategory.set(v || undefined);
  }

  protected onFilterDraftSource(event: Event): void {
    const v = (event.target as HTMLSelectElement).value as Source | '';
    this.filterDraftSource.set(v || undefined);
  }

  protected applyFilters(): void {
    this.store.dispatch(
      TransactionsPageActions.filtersCommitted({
        filterCategoryId: this.filterDraftCategory(),
        filterSource: this.filterDraftSource(),
      }),
    );
    this.filterOpen.set(false);
  }

  protected clearFilters(): void {
    this.filterDraftCategory.set(undefined);
    this.filterDraftSource.set(undefined);
    this.store.dispatch(TransactionsPageActions.filtersCleared());
    this.filterOpen.set(false);
  }

  protected activeCategoryLabel(): string {
    const id = this.filterCategoryId();
    if (!id) {
      return '';
    }
    return this.categoryById().get(id)?.name ?? id;
  }

  protected activeSourceLabel(): string {
    const src = this.filterSource();
    if (!src) {
      return '';
    }
    return SOURCE_LABELS[src] ?? src;
  }

  protected removeFilter(kind: 'category' | 'source'): void {
    this.store.dispatch(TransactionsPageActions.filterChipRemoved({ kind }));
  }

  protected goToPage(p: number): void {
    const totalPages = Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
    const next = Math.min(Math.max(1, p), totalPages);
    this.store.dispatch(TransactionsPageActions.pageChanged({ page: next }));
  }

  protected pageNumbers(): (number | 'ellipsis')[] {
    const totalPages = Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
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

  protected showingFrom(): number {
    if (this.totalCount() === 0) {
      return 0;
    }
    return (this.currentPage() - 1) * PAGE_SIZE + 1;
  }

  protected showingTo(): number {
    return Math.min(this.currentPage() * PAGE_SIZE, this.totalCount());
  }

  protected totalPages(): number {
    return Math.max(1, Math.ceil(this.totalCount() / PAGE_SIZE));
  }

  protected formatDate(iso: string): string {
    const [year, month, day] = iso.slice(0, 10).split('-').map(Number);
    const d = new Date(year, month - 1, day);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  protected formatTransactionCalendarDate(t: Transaction): string {
    const iso = t.transaction_date ?? t.created_at.slice(0, 10);
    return this.formatDate(iso);
  }
  protected formatMoney(amount: string, currency: string): string {
    const n = Number(amount);
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
      }).format(n);
    } catch {
      return `${currency} ${n.toFixed(2)}`;
    }
  }

  protected displayAmount(t: Transaction): string {
    const n = Number(t.amount);
    const formatted = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
    if (t.direction === 'INCOME') {
      return `+${formatted}`;
    }
    return `-${formatted}`;
  }

  protected amountClass(t: Transaction): string {
    return t.direction === 'INCOME' ? 'amount-income' : 'amount-expense';
  }

  protected sourceLabel(source: Source): string {
    const labels: Record<Source, string> = {
      BANK_ACCOUNT: 'Bank Account',
      CREDIT_CARD_NATIONAL: 'Visa National',
      CREDIT_CARD_INTERNATIONAL: 'Visa International',
      MERCADOPAGO: 'MercadoPago',
    };
    return labels[source];
  }

  protected sourceIcon(source: Source): string {
    return source === 'BANK_ACCOUNT' ? 'account_balance' : 'credit_card';
  }

  protected categoryLabel(t: Transaction): string {
    if (!t.category) {
      return 'Uncategorized';
    }
    return this.categoryById().get(t.category)?.name ?? 'Category';
  }

  protected categoryStyles(t: Transaction): Record<string, string> {
    const cat = t.category ? this.categoryById().get(t.category) : undefined;
    const hex = cat?.color ?? '#94a3b8';
    return {
      'background-color': `${hex}22`,
      color: hex,
      'border-color': `${hex}44`,
    };
  }

  protected categoryIcon(t: Transaction): string {
    const cat = t.category ? this.categoryById().get(t.category) : undefined;
    return cat?.icon ?? 'receipt';
  }

  @HostListener('document:click')
  protected closeMenu(): void {
    this.openMenuId.set(null);
  }

  protected toggleMenu(id: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.update((cur) => (cur === id ? null : id));
  }

  protected onEdit(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.editTarget.set(t);
  }

  protected onEditDismissed(): void {
    this.editTarget.set(null);
  }

  protected onEditSaveRequest(event: { id: string; payload: UpdateTransactionPayload }): void {
    this.store.dispatch(TransactionsPageActions.updateRequested(event));
  }

  protected onDelete(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.pendingDelete.set(t);
    this.deleteError.set(null);
    this.deleteModalOpen.set(true);
  }

  protected onMetadata(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.metadataTarget.set(t);
  }

  protected onMetadataDismissed(): void {
    this.metadataTarget.set(null);
  }

  protected closeDeleteModal(): void {
    if (this.deleteSubmitting()) return;
    this.deleteModalOpen.set(false);
    this.pendingDelete.set(null);
    this.deleteError.set(null);
  }

  protected confirmDelete(): void {
    const tx = this.pendingDelete();
    if (!tx) return;
    this.deleteSubmitting.set(true);
    this.deleteError.set(null);
    this.store.dispatch(TransactionsPageActions.deleteRequested({ id: tx.id }));
  }

  protected onSplit(t: Transaction, event: MouseEvent): void {
    event.stopPropagation();
    this.openMenuId.set(null);
    this.openSplitModal(t);
  }

  protected openSplitModal(t: Transaction): void {
    this.splitError.set(null);
    this.pendingSplit.set(t);
    this.splitForm.setControl(
      'rows',
      this.fb.array([this.createSplitRow(), this.createSplitRow()]),
    );
    this.splitModalOpen.set(true);
  }

  protected closeSplitModal(): void {
    this.splitModalOpen.set(false);
    this.pendingSplit.set(null);
    this.splitError.set(null);
  }

  protected get splitRows(): FormArray {
    return this.splitForm.get('rows') as FormArray;
  }

  protected addSplitRow(): void {
    this.splitRows.push(this.createSplitRow());
  }

  protected removeSplitRow(index: number): void {
    if (this.splitRows.length <= 2) {
      return;
    }
    this.splitRows.removeAt(index);
  }

  protected splitRowsTotal(): number {
    let sum = 0;
    for (const ctrl of this.splitRows.controls) {
      const g = ctrl as FormGroup;
      const raw = (g.get('amount')?.value as string | number | null | undefined) ?? '';
      const n = parseAmount(String(raw).trim());
      if (n !== null) {
        sum += n;
      }
    }
    return sum;
  }

  protected splitAmountsMatchTarget(): boolean {
    const p = this.pendingSplit();
    if (!p) {
      return false;
    }
    const target = round2(Number(p.amount));
    return Math.abs(this.splitRowsTotal() - target) < 0.0001;
  }

  protected canSubmitSplit(): boolean {
    if (!this.pendingSplit() || this.splitSubmitting()) {
      return false;
    }
    if (!this.splitAmountsMatchTarget()) {
      return false;
    }
    for (const ctrl of this.splitRows.controls) {
      const g = ctrl as FormGroup;
      if (g.invalid) {
        return false;
      }
    }
    return this.splitRows.length >= 2;
  }

  protected confirmSplit(): void {
    const bundle = this.pendingSplit();
    if (!bundle) {
      return;
    }
    this.splitForm.markAllAsTouched();
    if (!this.canSubmitSplit()) {
      this.splitError.set('Check all fields; amounts must sum to the original total.');
      return;
    }
    this.splitError.set(null);
    this.splitSubmitting.set(true);
    const items = this.splitRows.controls.map((ctrl) => {
      const g = ctrl as FormGroup;
      const desc = String(g.get('description')?.value ?? '').trim();
      const amountNum = round2(parseAmount(String(g.get('amount')?.value ?? '').trim()) ?? 0);
      const catRaw = g.get('category')?.value;
      const category =
        catRaw === null || catRaw === undefined || catRaw === '' ? null : String(catRaw);
      return {
        description: desc,
        amount: amountNum.toFixed(2),
        category,
      };
    });
    this.store.dispatch(
      TransactionsPageActions.splitRequested({ id: bundle.id, items }),
    );
  }

  protected openNewTxModal(): void {
    this.newTxError.set(null);
    this.newTxForm.reset({
      description: '',
      amount: '',
      currency: 'CLP',
      direction: 'EXPENSE',
      source: 'BANK_ACCOUNT',
      category: null,
      date: new Date().toISOString().slice(0, 10),
    });
    this.newTxModalOpen.set(true);
  }

  protected closeNewTxModal(): void {
    this.newTxModalOpen.set(false);
    this.newTxError.set(null);
  }

  protected openImportModal(): void {
    this.importModalOpen.set(true);
  }

  protected closeImportModal(): void {
    this.importModalOpen.set(false);
  }

  protected submitNewTx(): void {
    this.newTxForm.markAllAsTouched();
    if (this.newTxForm.invalid) {
      return;
    }
    const v = this.newTxForm.value;
    const direction = (v.direction ?? 'EXPENSE') as Direction;
    const txType: TransactionType = direction === 'INCOME' ? 'CREDIT' : 'DEBIT';
    const payload: CreateTransactionPayload = {
      description: String(v.description ?? '').trim(),
      amount: round2(Number(v.amount)).toFixed(2),
      currency: String(v.currency ?? 'USD'),
      direction,
      transaction_type: txType,
      source: (v.source ?? 'BANK_ACCOUNT') as Source,
      category: v.category ?? null,
      ...(v.date ? { transaction_date: v.date } : {}),
    };
    this.newTxSubmitting.set(true);
    this.newTxError.set(null);
    this.store.dispatch(TransactionsPageActions.createRequested({ payload }));
  }

  protected trendText(): string {
    const pct = this.trendVsPrevMonthPct();
    const less = this.trendSpentLess();
    if (pct === null && less === null) {
      return 'No comparison for last month';
    }
    if (less === null && pct === 0) {
      return 'Same as last month';
    }
    if (less === true) {
      return `${pct}% less than last month`;
    }
    return `${pct}% more than last month`;
  }
}

function parseAmount(s: string): number | null {
  if (!s) {
    return null;
  }
  const n = Number(s);
  if (Number.isNaN(n) || n <= 0) {
    return null;
  }
  return n;
}
