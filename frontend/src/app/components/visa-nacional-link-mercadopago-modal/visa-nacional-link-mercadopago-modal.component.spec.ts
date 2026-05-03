import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import type { MpPaymentSearchResponse } from '../../models/mercadopago.model';
import { MercadoPagoService } from '../../services/mercadopago.service';
import { ToastService } from '../../services/toast.service';
import { VisaNacionalLinkMercadoPagoModalComponent } from './visa-nacional-link-mercadopago-modal.component';

describe('VisaNacionalLinkMercadoPagoModalComponent', () => {
  const mockPayments: MpPaymentSearchResponse = {
    results: [
      {
        id: 90401,
        date_created: '2026-04-02T14:30:00.000Z',
        description: 'Test MP row',
        status: 'approved',
        currency_id: 'CLP',
        transaction_amount: 15000,
        transaction_details: { total_paid_amount: 15000 },
      },
    ],
    paging: { total: 1, offset: 0, limit: 30 },
  };

  beforeEach(async () => {
    const mpStub: Partial<MercadoPagoService> = {
      getPayments: () => of(mockPayments),
      linkToVisaTransaction: () =>
        of({
          stored_payment_id: 'a0000000-0000-0000-0000-000000000001',
          mp_payment_id: 90401,
          transaction_id: 'b0000000-0000-0000-0000-000000000002',
        }),
    };

    await TestBed.configureTestingModule({
      imports: [VisaNacionalLinkMercadoPagoModalComponent],
      providers: [
        { provide: MercadoPagoService, useValue: mpStub as MercadoPagoService },
        {
          provide: ToastService,
          useValue: {
            success: vi.fn(),
            error: vi.fn(),
          },
        },
      ],
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(VisaNacionalLinkMercadoPagoModalComponent);
    fixture.componentRef.setInput('transactionId', 'b2000000-0000-4000-8000-000000000001');
    fixture.detectChanges();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should show Mercado Pago linking title and table row', async () => {
    const fixture = TestBed.createComponent(VisaNacionalLinkMercadoPagoModalComponent);
    fixture.componentRef.setInput('transactionId', 'b2000000-0000-4000-8000-000000000001');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Link Mercado Pago payment');
    expect(el.textContent).toContain('Test MP row');
    expect(el.textContent).toContain('approved');
  });
});
