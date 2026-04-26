import { Routes } from '@angular/router';

import { authGuard } from './guards/auth.guard';
import { guestGuard } from './guards/guest.guard';
import { LoginComponent } from './pages/login/login.component';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { SignupComponent } from './pages/signup/signup.component';

export const routes: Routes = [
  { path: '', component: LoginComponent, canActivate: [guestGuard] },
  { path: 'login', redirectTo: '', pathMatch: 'full' },
  { path: 'signup', component: SignupComponent, canActivate: [guestGuard] },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'connections', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'transactions', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'projections', component: DashboardComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: '' },
];
