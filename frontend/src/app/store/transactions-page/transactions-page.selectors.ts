import { createSelector } from '@ngrx/store';

import { transactionsPageFeature } from './transactions-page.reducer';

export const selectSpendTotalsAndTrend = createSelector(
  transactionsPageFeature.selectTotalsByCurrency,
  transactionsPageFeature.selectPrevTotalsByCurrency,
  transactionsPageFeature.selectTotalSpent,
  (totals_by_currency, prev_totals_by_currency, total_spent) => {
    const prev = prev_totals_by_currency ?? {};

    let rows: { currency: string; amount: number }[];

    if (totals_by_currency != null) {
      if (Object.keys(totals_by_currency).length > 0) {
        rows = Object.keys(totals_by_currency)
          .sort()
          .map((currency) => ({
            currency,
            amount: Number(totals_by_currency[currency] ?? '0'),
          }));
      } else {
        rows = [];
      }
    } else if (total_spent != null) {
      rows = [{ currency: 'USD', amount: Number(total_spent ?? '0') }];
    } else {
      rows = [];
    }

    let trendPct: number | null = null;
    let trendSpentLess: boolean | null = null;

    if (rows.length === 1) {
      const { currency } = rows[0];
      const spentThis = rows[0].amount;
      const spentPrev = Number(prev[currency] ?? '0');
      if (spentPrev <= 0) {
        trendPct = null;
        trendSpentLess = null;
      } else if (spentThis < spentPrev) {
        trendPct = Math.round(((spentPrev - spentThis) / spentPrev) * 100 * 10) / 10;
        trendSpentLess = true;
      } else if (spentThis > spentPrev) {
        trendPct = Math.round(((spentThis - spentPrev) / spentPrev) * 100 * 10) / 10;
        trendSpentLess = false;
      } else {
        trendPct = 0;
        trendSpentLess = null;
      }
    }

    return { rows, trendPct, trendSpentLess };
  },
);
