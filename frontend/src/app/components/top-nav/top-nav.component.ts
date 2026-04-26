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

  protected readonly menuOpen = signal(false);

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as Node | null;
    const root = this.userMenuRoot().nativeElement;
    if (target && root.contains(target)) {
      return;
    }
    this.menuOpen.set(false);
  }

  protected toggleUserMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen.update((open) => !open);
  }

  protected signOut(): void {
    this.menuOpen.set(false);
    this.auth.signOut();
    void this.router.navigate(['']);
  }
}
