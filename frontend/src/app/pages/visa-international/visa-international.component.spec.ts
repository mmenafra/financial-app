import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { VisaInternationalComponent } from './visa-international.component';

describe('VisaInternationalComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VisaInternationalComponent],
      providers: [provideHttpClient(), provideRouter([])],
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
