import { Component } from '@angular/core';

import { SidebarComponent } from '../../components/sidebar/sidebar.component';
import { TopNavComponent } from '../../components/top-nav/top-nav.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [SidebarComponent, TopNavComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent {}
