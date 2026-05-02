import { inject, Injectable } from '@angular/core';
import { Actions, createEffect, ofType } from '@ngrx/effects';
import { Store } from '@ngrx/store';
import { catchError, concat, forkJoin, from, map, of, switchMap, take, tap } from 'rxjs';

import { ToastService } from '../../services/toast.service';
import { TransactionService } from '../../services/transaction.service';
import { httpErrorMessage } from '../../utils/transaction-edit';
import { TransactionsPageActions } from './transactions-page.actions';
import { transactionsPageFeature } from './transactions-page.reducer';
import { TRANSACTIONS_PAGE_SIZE } from './transactions-page.state';

@Injectable()
export class TransactionsPageEffects {
  private readonly actions$ = inject(Actions);
  private readonly store = inject(Store);
  private readonly transactionService = inject(TransactionService);
  private readonly toast = inject(ToastService);

  readonly loadList$ = createEffect(() =>
    this.actions$.pipe(
      ofType(
        TransactionsPageActions.initialized,
        TransactionsPageActions.yearChanged,
        TransactionsPageActions.monthChanged,
        TransactionsPageActions.filtersCommitted,
        TransactionsPageActions.filtersCleared,
        TransactionsPageActions.filterChipRemoved,
        TransactionsPageActions.pageChanged,
        TransactionsPageActions.listRefreshRequested,
        TransactionsPageActions.importCompleted,
      ),
      switchMap(() =>
        this.store.select(transactionsPageFeature.selectTransactionsPageState).pipe(
          take(1),
          switchMap((state) => {
            const filters = {
              year: state.year,
              month: state.month,
              category: state.filterCategoryId,
              source: state.filterSource,
              page: state.page,
              pageSize: TRANSACTIONS_PAGE_SIZE,
            };
            const data$ = state.categoriesLoaded
              ? this.transactionService.getTransactions(filters).pipe(
                  map((p) =>
                    TransactionsPageActions.loadSucceeded({
                      transactions: p.results,
                      totalCount: p.count,
                      totalsByCurrency: p.totals_by_currency,
                      prevTotalsByCurrency: p.prev_totals_by_currency,
                      totalSpent: p.total_spent,
                    }),
                  ),
                  catchError(() =>
                    of(
                      TransactionsPageActions.loadFailed({
                        message: 'Could not load transactions. Try again.',
                      }),
                    ),
                  ),
                )
              : forkJoin({
                  categories: this.transactionService.getCategories(),
                  page: this.transactionService.getTransactions(filters),
                }).pipe(
                  map(({ categories, page: p }) =>
                    TransactionsPageActions.loadSucceeded({
                      transactions: p.results,
                      totalCount: p.count,
                      totalsByCurrency: p.totals_by_currency,
                      prevTotalsByCurrency: p.prev_totals_by_currency,
                      totalSpent: p.total_spent,
                      categories,
                    }),
                  ),
                  catchError(() =>
                    of(
                      TransactionsPageActions.loadFailed({
                        message: 'Could not load transactions. Try again.',
                      }),
                    ),
                  ),
                );
            return concat(of(TransactionsPageActions.loadStarted()), data$);
          }),
        ),
      ),
    ),
  );

  readonly loadFailedToast$ = createEffect(
    () =>
      this.actions$.pipe(
        ofType(TransactionsPageActions.loadFailed),
        tap(({ message }) => this.toast.error(message)),
      ),
    { dispatch: false },
  );

  readonly summaryRefresh$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.summaryRefreshRequested),
      switchMap(() =>
        this.store.select(transactionsPageFeature.selectTransactionsPageState).pipe(
          take(1),
          switchMap((state) =>
            this.transactionService
              .getTransactions({
                year: state.year,
                month: state.month,
                category: state.filterCategoryId,
                source: state.filterSource,
                page: state.page,
                pageSize: TRANSACTIONS_PAGE_SIZE,
              })
              .pipe(
                map((p) =>
                  TransactionsPageActions.summaryLoadSucceeded({
                    totalCount: p.count,
                    totalsByCurrency: p.totals_by_currency,
                    prevTotalsByCurrency: p.prev_totals_by_currency,
                    totalSpent: p.total_spent,
                  }),
                ),
                catchError(() => of(TransactionsPageActions.listRefreshRequested())),
              ),
          ),
        ),
      ),
    ),
  );

  readonly afterLocalDelete$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.deleteMutationSucceeded),
      switchMap(() =>
        this.store.select(transactionsPageFeature.selectTransactionsPageState).pipe(
          take(1),
          map((state) =>
            state.transactions.length === 0
              ? TransactionsPageActions.listRefreshRequested()
              : TransactionsPageActions.summaryRefreshRequested(),
          ),
        ),
      ),
    ),
  );

  readonly delete$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.deleteRequested),
      switchMap(({ id }) =>
        this.transactionService.deleteTransaction(id).pipe(
          tap(() => this.toast.success('Transaction deleted')),
          map(() => TransactionsPageActions.deleteMutationSucceeded({ id })),
          catchError((err: unknown) =>
            of(
              TransactionsPageActions.deleteMutationFailed({
                message: httpErrorMessage(err) ?? 'Could not delete transaction.',
              }),
            ),
          ),
        ),
      ),
    ),
  );

  readonly update$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.updateRequested),
      switchMap(({ id, payload }) =>
        this.transactionService.updateTransaction(id, payload).pipe(
          tap(() => this.toast.success('Changes saved')),
          switchMap((transaction) =>
            from([
              TransactionsPageActions.updateMutationSucceeded({ transaction }),
              TransactionsPageActions.summaryRefreshRequested(),
            ]),
          ),
          catchError((err: unknown) =>
            of(
              TransactionsPageActions.updateMutationFailed({
                message: httpErrorMessage(err) ?? 'Could not update transaction.',
              }),
            ),
          ),
        ),
      ),
    ),
  );

  readonly create$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.createRequested),
      switchMap(({ payload }) =>
        this.transactionService.createTransaction(payload).pipe(
          tap(() => this.toast.success('Transaction created')),
          switchMap(() =>
            from([
              TransactionsPageActions.createMutationSucceeded(),
              TransactionsPageActions.listRefreshRequested(),
            ]),
          ),
          catchError((err: unknown) =>
            of(
              TransactionsPageActions.createMutationFailed({
                message: httpErrorMessage(err) ?? 'Could not create transaction.',
              }),
            ),
          ),
        ),
      ),
    ),
  );

  readonly split$ = createEffect(() =>
    this.actions$.pipe(
      ofType(TransactionsPageActions.splitRequested),
      switchMap(({ id, items }) =>
        this.store.select(transactionsPageFeature.selectTransactionsPageState).pipe(
          take(1),
          switchMap((pageState) => {
            const parentOnPage = pageState.transactions.some((x) => x.id === id);
            return this.transactionService.splitTransaction(id, items).pipe(
              tap(() => this.toast.success('Transaction split')),
              switchMap((newTransactions) =>
                parentOnPage
                  ? from([
                      TransactionsPageActions.splitMutationSucceeded({
                        parentId: id,
                        transactions: newTransactions,
                      }),
                      TransactionsPageActions.summaryRefreshRequested(),
                    ])
                  : of(TransactionsPageActions.listRefreshRequested()),
              ),
              catchError((err: unknown) =>
                of(
                  TransactionsPageActions.splitMutationFailed({
                    message: httpErrorMessage(err) ?? 'Could not split transaction.',
                  }),
                ),
              ),
            );
          }),
        ),
      ),
    ),
  );
}
