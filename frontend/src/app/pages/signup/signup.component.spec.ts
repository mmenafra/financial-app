import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';

import { SignupComponent } from './signup.component';
import { DashboardComponent } from '../dashboard/dashboard.component';

const API_SIGNUP = 'http://localhost:8000/api/auth/signup/';

function mockGoogleIdentityService(): void {
  window.google = {
    accounts: {
      id: {
        initialize: vi.fn(),
        prompt: vi.fn(),
      },
    },
  };
}

const MOCK_SUCCESS = {
  user: { id: 1, username: 'testuser', email: 'test@example.com' },
  tokens: { access: 'access-token', refresh: 'refresh-token' },
};

describe('SignupComponent', () => {
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    mockGoogleIdentityService();
    await TestBed.configureTestingModule({
      imports: [SignupComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'dashboard', component: DashboardComponent }]),
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate');

    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(SignupComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the signup heading', () => {
    const fixture = TestBed.createComponent(SignupComponent);
    fixture.detectChanges();
    const heading = fixture.debugElement.query(By.css('h2'));
    expect(heading.nativeElement.textContent).toContain('Create your account');
  });

  describe('form validation', () => {
    it('should not submit and should mark fields as touched when form is empty', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.submit();

      expect(component.form.touched).toBe(true);
      httpMock.expectNone(API_SIGNUP);
    });

    it('should not submit when passwords do not match', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({
        username: 'u',
        email: 'a@b.com',
        password: '12345678',
        passwordConfirm: '87654321',
        rememberMe: false,
      });
      component.submit();

      expect(component.form.hasError('passwordMismatch')).toBe(true);
      httpMock.expectNone(API_SIGNUP);
    });
  });

  describe('successful sign-up', () => {
    it('should POST to the signup endpoint with username, email, and password', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({
        username: 'testuser',
        email: 'test@example.com',
        password: 'secret123',
        passwordConfirm: 'secret123',
        rememberMe: false,
      });
      component.submit();

      const req = httpMock.expectOne(API_SIGNUP);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({
        username: 'testuser',
        email: 'test@example.com',
        password: 'secret123',
      });
      req.flush(MOCK_SUCCESS, { status: 201, statusText: 'Created' });
    });

    it('should navigate to /dashboard after a successful sign-up', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({
        username: 'testuser',
        email: 'test@example.com',
        password: 'secret123',
        passwordConfirm: 'secret123',
        rememberMe: false,
      });
      component.submit();

      httpMock
        .expectOne(API_SIGNUP)
        .flush(MOCK_SUCCESS, { status: 201, statusText: 'Created' });

      expect(router.navigate).toHaveBeenCalledWith(['/dashboard']);
    });

    it('should show field error message on 400 from API', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({
        username: 'x',
        email: 'taken@example.com',
        password: 'secret123',
        passwordConfirm: 'secret123',
        rememberMe: false,
      });
      component.submit();

      httpMock.expectOne(API_SIGNUP).flush(
        { email: ['A user with this email already exists.'] },
        { status: 400, statusText: 'Bad Request' },
      );
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('A user with this email already exists.');
    });
  });

  describe('show/hide password toggle', () => {
    it('should toggle showPassword signal', () => {
      const fixture = TestBed.createComponent(SignupComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.showPassword()).toBe(false);
      component.togglePassword();
      expect(component.showPassword()).toBe(true);
    });
  });
});
