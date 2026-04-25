import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';

import { LoginComponent } from './login.component';
import { DashboardComponent } from '../dashboard/dashboard.component';

const API_SIGNIN = 'http://localhost:8000/api/auth/signin/';

const MOCK_SUCCESS = {
  user: { id: 1, username: 'testuser', email: 'test@example.com' },
  tokens: { access: 'access-token', refresh: 'refresh-token' },
};

describe('LoginComponent', () => {
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'dashboard', component: DashboardComponent }]),
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate');

    // Clean up any stored tokens between tests
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the component', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the login heading', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const heading = fixture.debugElement.query(By.css('h2'));
    expect(heading.nativeElement.textContent).toContain('Secure Login');
  });

  describe('form validation', () => {
    it('should not submit and should mark fields as touched when form is empty', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.submit();

      expect(component.form.touched).toBe(true);
      expect(component.usernameControl.touched).toBe(true);
      expect(component.passwordControl.touched).toBe(true);
      httpMock.expectNone(API_SIGNIN);
    });

    it('should not submit when only username is filled', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.controls.username.setValue('someone');
      component.submit();

      httpMock.expectNone(API_SIGNIN);
    });
  });

  describe('successful sign-in', () => {
    it('should POST to the signin endpoint with username and password', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'testuser', password: 'secret123', rememberMe: false });
      component.submit();

      const req = httpMock.expectOne(API_SIGNIN);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ username: 'testuser', password: 'secret123' });
      req.flush(MOCK_SUCCESS);
    });

    it('should navigate to /dashboard after a successful sign-in', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'testuser', password: 'secret123', rememberMe: false });
      component.submit();

      httpMock.expectOne(API_SIGNIN).flush(MOCK_SUCCESS);

      expect(router.navigate).toHaveBeenCalledWith(['/dashboard']);
    });

    it('should store tokens in sessionStorage when rememberMe is false', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'testuser', password: 'secret123', rememberMe: false });
      component.submit();
      httpMock.expectOne(API_SIGNIN).flush(MOCK_SUCCESS);

      expect(sessionStorage.getItem('auth_access')).toBe('access-token');
    });

    it('should store tokens in localStorage when rememberMe is true', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'testuser', password: 'secret123', rememberMe: true });
      component.submit();
      httpMock.expectOne(API_SIGNIN).flush(MOCK_SUCCESS);

      expect(localStorage.getItem('auth_access')).toBe('access-token');
    });

    it('should clear errorMessage on a successful sign-in', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      // Simulate a prior error
      component.errorMessage.set('Previous error');

      component.form.setValue({ username: 'testuser', password: 'secret123', rememberMe: false });
      component.submit();
      httpMock.expectOne(API_SIGNIN).flush(MOCK_SUCCESS);

      expect(component.errorMessage()).toBe('');
    });
  });

  describe('failed sign-in', () => {
    it('should show an error message on 401 and NOT navigate', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'wrong', password: 'bad', rememberMe: false });
      component.submit();

      httpMock.expectOne(API_SIGNIN).flush(
        { detail: 'Invalid credentials.' },
        { status: 401, statusText: 'Unauthorized' },
      );
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Invalid username or password. Please try again.');
      expect(router.navigate).not.toHaveBeenCalled();
    });

    it('should show a generic error message on non-401 errors', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'user', password: 'pass', rememberMe: false });
      component.submit();

      httpMock.expectOne(API_SIGNIN).flush(
        { detail: 'Server error.' },
        { status: 500, statusText: 'Internal Server Error' },
      );
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Something went wrong. Please try again later.');
    });

    it('should render the error message in the template on 401', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'wrong', password: 'bad', rememberMe: false });
      component.submit();
      httpMock.expectOne(API_SIGNIN).flush(
        { detail: 'Invalid credentials.' },
        { status: 401, statusText: 'Unauthorized' },
      );
      fixture.detectChanges();

      const alert = fixture.debugElement.query(By.css('[role="alert"]'));
      expect(alert).toBeTruthy();
      expect(alert.nativeElement.textContent).toContain('Invalid username or password');
    });

    it('should set loading to false after a failed request', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({ username: 'user', password: 'pass', rememberMe: false });
      component.submit();
      expect(component.loading()).toBe(true);

      httpMock.expectOne(API_SIGNIN).flush(
        {},
        { status: 401, statusText: 'Unauthorized' },
      );

      expect(component.loading()).toBe(false);
    });
  });

  describe('show/hide password toggle', () => {
    it('should toggle showPassword signal', () => {
      const fixture = TestBed.createComponent(LoginComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.showPassword()).toBe(false);
      component.togglePassword();
      expect(component.showPassword()).toBe(true);
      component.togglePassword();
      expect(component.showPassword()).toBe(false);
    });
  });
});
