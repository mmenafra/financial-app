import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { environment } from '../../../environments/environment';
import { AuthService } from '../../services/auth.service';

const GOOGLE_SCRIPT_WAIT_MS = 10_000;
const GOOGLE_SCRIPT_POLL_MS = 50;

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  form = this.fb.nonNullable.group({
    username: ['', [Validators.required]],
    password: ['', [Validators.required]],
    rememberMe: [false],
  });

  loading = signal(false);
  errorMessage = signal('');
  showPassword = signal(false);
  googleLoading = signal(false);
  googleReady = signal(false);

  private googleInitialized = false;

  ngOnInit(): void {
    if (this.auth.isAuthenticated()) {
      void this.router.navigate(['/dashboard'], { replaceUrl: true });
      return;
    }
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
    this.auth.loginWithGoogle(response.credential, false).subscribe({
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

  get passwordControl() {
    return this.form.controls.password;
  }

  signInWithGoogle(): void {
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

    const { username, password, rememberMe } = this.form.getRawValue();

    this.auth.signIn({ username, password }, rememberMe).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.loading.set(false);
        if (err.status === 401) {
          this.errorMessage.set('Invalid username or password. Please try again.');
        } else {
          this.errorMessage.set('Something went wrong. Please try again later.');
        }
      },
    });
  }
}
