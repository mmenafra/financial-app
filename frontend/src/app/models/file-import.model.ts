import type { BankStatementImportResult, PaginatedResponse, Source } from './transaction.model';

/** Mirrors `FileImportSerializer` / `FileImport` model. */
export type ImportRecordStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface FileImportRow {
  id: string;
  created_at: string;
  updated_at: string;
  user: number;
  source: Source;
  /** Absolute or relative URL from API */
  file: string;
  original_filename: string;
  status: ImportRecordStatus;
  rows_imported: number;
  rows_skipped: number;
  error_message: string | null;
}

export type FileImportListResponse = PaginatedResponse<FileImportRow>;

/** POST /api/file-imports/:id/re-run/ */
export interface FileImportRerunResponse {
  file_import: FileImportRow;
  import_result?: BankStatementImportResult;
  detail?: string;
}
