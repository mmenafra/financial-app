import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import type { VisaInternationalDashboardResponse } from '../../models/transaction.model';
import { TransactionService } from '../../services/transaction.service';
import { VisaInternationalComponent } from './visa-international.component';

function emptyVisaDashboard(): VisaInternationalDashboardResponse {
  const monthly_totals = [];
  let y = 2026;
  let m = 4;
  for (let i = 0; i < 12; i++) {
    monthly_totals.push({ year: y, month: m, total: '0' });
    m -= 1;
    if (m < 1) {
      m = 12;
      y -= 1;
    }
  }
  monthly_totals.reverse();
  return {
    statement: null,
    transactions: [],
    monthly_totals,
  };
}

describe('VisaInternationalComponent', () => {
  const mockPattern = {
    id: '00000000-0000-0000-0000-000000000001',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    user: 1,
    description_pattern: 'TEST',
    expected_amount: null,
    frequency: 'MONTHLY' as const,
    match_type: 'PARTIAL' as const,
  };

  const txStub: Partial<TransactionService> = {
    getCategories: () => of([]),
    getRecurringPatterns: () => of([]),
    createRecurringPattern: () => of(mockPattern),
    getVisaInternationalDashboard: () => of(emptyVisaDashboard()),
    importVisaInternational: () =>
      of({
        created: 0,
        skipped: 0,
        failed: 0,
        transactions: [],
        errors: [],
      }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VisaInternationalComponent],
      providers: [
        provideHttpClient(),
        { provide: TransactionService, useValue: txStub as TransactionService },
        provideRouter([]),
      ],
    }).compileComponents();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(VisaInternationalComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should show Visa International heading', () => {
    const fixture = TestBed.createComponent(VisaInternationalComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Visa International');
  });
});
