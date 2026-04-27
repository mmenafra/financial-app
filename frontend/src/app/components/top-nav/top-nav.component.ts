import { Component, ElementRef, HostListener, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-top-nav',
  standalone: true,
  imports: [],
  templateUrl: './top-nav.component.html',
  styleUrl: './top-nav.component.scss',
})
export class TopNavComponent {
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly userMenuRoot = viewChild.required<ElementRef<HTMLElement>>('userMenuRoot');
  private readonly settingsMenuRoot = viewChild.required<ElementRef<HTMLElement>>('settingsMenuRoot');

  protected readonly menuOpen = signal(false);
  protected readonly settingsMenuOpen = signal(false);

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as Node | null;
    const userRoot = this.userMenuRoot().nativeElement;
    const settingsRoot = this.settingsMenuRoot().nativeElement;
    if (target && userRoot.contains(target)) {
      return;
    }
    if (target && settingsRoot.contains(target)) {
      return;
    }
    this.menuOpen.set(false);
    this.settingsMenuOpen.set(false);
  }

  protected toggleUserMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen.update((open) => !open);
    if (this.menuOpen()) {
      this.settingsMenuOpen.set(false);
    }
  }

  protected toggleSettingsMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.settingsMenuOpen.update((open) => !open);
    if (this.settingsMenuOpen()) {
      this.menuOpen.set(false);
    }
  }

  protected goToImports(): void {
    this.settingsMenuOpen.set(false);
    void this.router.navigate(['/imports']);
  }

  protected signOut(): void {
    this.menuOpen.set(false);
    this.settingsMenuOpen.set(false);
    this.auth.signOut();
    void this.router.navigate(['']);
  }
}
