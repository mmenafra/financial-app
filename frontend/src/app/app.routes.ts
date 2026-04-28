import { Routes } from '@angular/router';

import { authGuard } from './guards/auth.guard';
import { guestGuard } from './guards/guest.guard';
import { LoginComponent } from './pages/login/login.component';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { SignupComponent } from './pages/signup/signup.component';
import { TransactionsComponent } from './pages/transactions/transactions.component';
import { CategoriesComponent } from './pages/categories/categories.component';
import { ImportsComponent } from './pages/imports/imports.component';
import { SettingsComponent } from './pages/settings/settings.component';
import { VisaInternationalComponent } from './pages/visa-international/visa-international.component';

export const routes: Routes = [
  { path: '', component: LoginComponent, canActivate: [guestGuard] },
  { path: 'login', redirectTo: '', pathMatch: 'full' },
  { path: 'signup', component: SignupComponent, canActivate: [guestGuard] },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'connections', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'transactions', component: TransactionsComponent, canActivate: [authGuard] },
  {
    path: 'visa-international',
    component: VisaInternationalComponent,
    canActivate: [authGuard],
  },
  { path: 'categories', component: CategoriesComponent, canActivate: [authGuard] },
  { path: 'imports', component: ImportsComponent, canActivate: [authGuard] },
  { path: 'settings', component: SettingsComponent, canActivate: [authGuard] },
  { path: 'projections', component: DashboardComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: '' },
];
