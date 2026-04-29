import type { Source } from '../models/transaction.model';

/** Copy and file accept hints matching Transactions / Visa import modals — for re-run on Imports page. */
export const IMPORT_SOURCE_PRESETS: Record<
  Source,
  { accept: string; modalTitle: string; modalDescription: string }
> = {
  BANK_ACCOUNT: {
    accept: '.dat',
    modalTitle: 'Import bank statement',
    modalDescription:
      'Select a bank export (.dat) file. Existing lines are skipped automatically; new rows are added with your categories when descriptions match past transactions.',
  },
  CREDIT_CARD_NATIONAL: {
    accept: '.pdf',
    modalTitle: 'Import Visa Nacional statement',
    modalDescription:
      'Select a Scotia Visa Nacional (CLP) statement PDF. Existing references are skipped; descriptions match prior categories where possible.',
  },
  CREDIT_CARD_INTERNATIONAL: {
    accept: '.pdf',
    modalTitle: 'Import Visa International statement',
    modalDescription:
      'Select a Scotia Visa Internacional (USD) statement PDF. Existing references are skipped; descriptions match prior categories where possible.',
  },
  MERCADOPAGO: {
    accept: '.dat,.pdf,.csv',
    modalTitle: 'Import',
    modalDescription:
      'Re-process this import to view results and categorize transactions.',
  },
};

export function presetsForImportSource(source: Source): typeof IMPORT_SOURCE_PRESETS[Source] {
  return IMPORT_SOURCE_PRESETS[source] ?? IMPORT_SOURCE_PRESETS.BANK_ACCOUNT;
}
