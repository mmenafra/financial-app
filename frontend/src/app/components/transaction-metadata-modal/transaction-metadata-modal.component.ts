import { CommonModule } from '@angular/common';
import { Component, computed, input, output } from '@angular/core';

import type { Transaction } from '../../models/transaction.model';

@Component({
  selector: 'app-transaction-metadata-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './transaction-metadata-modal.component.html',
  styleUrl: './transaction-metadata-modal.component.scss',
})
export class TransactionMetadataModalComponent {
  readonly transaction = input<Transaction | null>(null);
  readonly idPrefix = input('tx');

  readonly dismissed = output<void>();

  protected readonly titleId = computed(() => `${this.idPrefix()}-tx-metadata-title`);

  protected debugJson(t: Transaction): string {
    return JSON.stringify(t, null, 2);
  }

  protected closeModal(): void {
    this.dismissed.emit();
  }
}
