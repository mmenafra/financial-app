import type { BankStatementImportResult } from '../models/transaction.model';

/**
 * Ensures `skipped_items` is populated — API payloads may use `skippedItems`
 * or omit the array while still returning `skipped > 0`.
 */
export function normalizeBankStatementImportResult(
  raw: BankStatementImportResult,
): BankStatementImportResult {
  const loose = raw as unknown as Record<string, unknown>;
  const skippedRaw = loose['skipped_items'] ?? loose['skippedItems'];
  const skipped_items = Array.isArray(skippedRaw)
    ? (skippedRaw as NonNullable<BankStatementImportResult['skipped_items']>)
    : [];
  return {
    ...raw,
    skipped_items,
  };
}
