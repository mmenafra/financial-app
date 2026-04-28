import { CommonModule } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';
import { UserProfileService } from '../../services/user-profile.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent, TopNavComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {
  private readonly userProfileService = inject(UserProfileService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly hasGeminiKey = signal(false);
  protected readonly isLoading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly saveError = signal<string | null>(null);
  protected readonly saveSuccess = signal(false);
  protected readonly isSaving = signal(false);
  protected readonly isRemoving = signal(false);

  /** Never populated from the server — only what the user types before save. */
  protected newApiKey = '';

  constructor() {
    this.reloadProfile();
  }

  protected reloadProfile(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.userProfileService
      .getProfile()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (p) => {
          this.hasGeminiKey.set(p.has_gemini_key);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.loadError.set(this.errorMessage(err));
        },
      });
  }

  protected saveKey(): void {
    this.saveError.set(null);
    this.saveSuccess.set(false);
    this.isSaving.set(true);
    this.userProfileService
      .saveGeminiApiKey(this.newApiKey.trim())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (p) => {
          this.hasGeminiKey.set(p.has_gemini_key);
          this.newApiKey = '';
          this.isSaving.set(false);
          this.saveSuccess.set(true);
        },
        error: (err: unknown) => {
          this.isSaving.set(false);
          this.saveError.set(this.errorMessage(err));
        },
      });
  }

  protected removeKey(): void {
    this.saveError.set(null);
    this.saveSuccess.set(false);
    this.isRemoving.set(true);
    this.userProfileService
      .saveGeminiApiKey('')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (p) => {
          this.hasGeminiKey.set(p.has_gemini_key);
          this.newApiKey = '';
          this.isRemoving.set(false);
          this.saveSuccess.set(true);
        },
        error: (err: unknown) => {
          this.isRemoving.set(false);
          this.saveError.set(this.errorMessage(err));
        },
      });
  }

  private errorMessage(err: unknown): string {
    if (err && typeof err === 'object' && 'error' in err) {
      const e = err as { error?: { detail?: string } };
      if (e.error?.detail) {
        return e.error.detail;
      }
    }
    return 'Something went wrong. Please try again.';
  }
}
