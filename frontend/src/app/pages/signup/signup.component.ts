import { Component, inject, OnInit, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  ValidatorFn,
  Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { environment } from '../../../environments/environment';
import { AuthService } from '../../services/auth.service';

const GOOGLE_SCRIPT_WAIT_MS = 10_000;
const GOOGLE_SCRIPT_POLL_MS = 50;

const passwordsMatchValidator: ValidatorFn = (
  group: AbstractControl,
): ValidationErrors | null => {
  const password = group.get('password')?.value as string | undefined;
  const passwordConfirm = group.get('passwordConfirm')?.value as string | undefined;
  if (!passwordConfirm) {
    return null;
  }
  return password === passwordConfirm ? null : { passwordMismatch: true };
};

function firstApiErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') {
    return null;
  }
  const o = body as Record<string, unknown>;
  for (const key of ['non_field_errors', 'email', 'username', 'password', 'detail']) {
    const v = o[key];
    if (Array.isArray(v) && v.length > 0 && typeof v[0] === 'string') {
      return v[0];
    }
    if (typeof v === 'string') {
      return v;
    }
  }
  for (const val of Object.values(o)) {
    if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'string') {
      return val[0];
    }
  }
  return null;
}

@Component({
  selector: 'app-signup',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './signup.component.html',
  styleUrl: './signup.component.scss',
})
export class SignupComponent implements OnInit {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  form = this.fb.nonNullable.group(
    {
      username: ['', [Validators.required]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(8)]],
      passwordConfirm: ['', [Validators.required]],
      rememberMe: [false],
    },
    { validators: [passwordsMatchValidator] },
  );

  loading = signal(false);
  errorMessage = signal('');
  showPassword = signal(false);
  googleLoading = signal(false);
  googleReady = signal(false);

  private googleInitialized = false;

  ngOnInit(): void {
    if (!environment.googleClientId) {
      return;
    }
    this.waitForGoogleScript()
      .then(() => {
        const g = window.google?.accounts?.id;
        if (!g) {
          return;
        }
        g.initialize({
          client_id: environment.googleClientId,
          auto_select: false,
          cancel_on_tap_outside: true,
          callback: (response) => this.onGoogleCredential(response),
        });
        this.googleInitialized = true;
        this.googleReady.set(true);
      })
      .catch(() => {
        this.googleReady.set(false);
      });
  }

  private waitForGoogleScript(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (window.google?.accounts?.id) {
        resolve();
        return;
      }
      let waited = 0;
      const t = setInterval(() => {
        if (window.google?.accounts?.id) {
          clearInterval(t);
          resolve();
        } else {
          waited += GOOGLE_SCRIPT_POLL_MS;
          if (waited >= GOOGLE_SCRIPT_WAIT_MS) {
            clearInterval(t);
            reject(new Error('Google sign-in script did not load.'));
          }
        }
      }, GOOGLE_SCRIPT_POLL_MS);
    });
  }

  private onGoogleCredential(response: { credential: string }): void {
    this.googleLoading.set(false);
    if (!response.credential) {
      this.errorMessage.set('Google did not return a sign-in token.');
      return;
    }
    this.errorMessage.set('');
    const { rememberMe } = this.form.getRawValue();
    this.auth.loginWithGoogle(response.credential, rememberMe).subscribe({
      next: () => {
        this.router.navigate(['/dashboard']);
      },
      error: (err: { status?: number; error?: { detail?: string } }) => {
        if (err.status === 401) {
          this.errorMessage.set('Could not sign in with Google. Please try again.');
        } else if (err.status === 400) {
          this.errorMessage.set(
            err.error?.detail ?? 'Google sign-in was rejected. Please try again.',
          );
        } else if (err.status === 503) {
          this.errorMessage.set('Google sign-in is not available on the server right now.');
        } else {
          this.errorMessage.set('Something went wrong. Please try again later.');
        }
      },
    });
  }

  get usernameControl() {
    return this.form.controls.username;
  }

  get emailControl() {
    return this.form.controls.email;
  }

  get passwordControl() {
    return this.form.controls.password;
  }

  get passwordConfirmControl() {
    return this.form.controls.passwordConfirm;
  }

  signUpWithGoogle(): void {
    this.errorMessage.set('');
    if (!environment.googleClientId) {
      this.errorMessage.set('Google sign-in is not configured for this app.');
      return;
    }
    if (!this.googleInitialized || !window.google?.accounts?.id) {
      this.errorMessage.set('Google sign-in is still loading. Please wait and try again.');
      return;
    }
    this.googleLoading.set(true);
    window.google.accounts.id.prompt((notification) => {
      if (
        notification.isNotDisplayed() ||
        notification.isSkippedMoment() ||
        notification.isDismissedMoment()
      ) {
        this.googleLoading.set(false);
      }
    });
  }

  togglePassword(): void {
    this.showPassword.update((v) => !v);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading.set(true);
    this.errorMessage.set('');

    const { username, email, password, rememberMe } = this.form.getRawValue();

    this.auth.signUp({ username, email, password }, rememberMe).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/dashboard']);
      },
      error: (err: { status?: number; error?: unknown }) => {
        this.loading.set(false);
        if (err.status === 400) {
          const msg = firstApiErrorMessage(err.error);
          this.errorMessage.set(
            msg ?? 'Please check your details and try again.',
          );
        } else {
          this.errorMessage.set('Something went wrong. Please try again later.');
        }
      },
    });
  }
}
