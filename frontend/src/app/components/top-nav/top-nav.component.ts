import { Component, ElementRef, HostListener, inject, signal, viewChild } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

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

  protected readonly pageTitle = signal('Dashboard');
  protected readonly menuOpen = signal(false);

  constructor() {
    this.updateTitle(this.router.url);
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => this.updateTitle(e.urlAfterRedirects));
  }

  private updateTitle(url: string): void {
    const segment = url.split('?')[0].split('/').filter(Boolean).pop() ?? 'dashboard';
    const titles: Record<string, string> = {
      dashboard: 'Dashboard',
      connections: 'Connections',
      transactions: 'Transaction History',
      projections: 'Projections',
    };
    this.pageTitle.set(titles[segment] ?? 'Dashboard');
  }

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
