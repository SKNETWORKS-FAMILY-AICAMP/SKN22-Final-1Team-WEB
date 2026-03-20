import { createBrowserRouter } from 'react-router';
import { AdminLoginPage } from './pages/AdminLoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { CustomerListPage } from './pages/CustomerListPage';
import { CustomerSearchPage } from './pages/CustomerSearchPage';
import { CustomerDetailPage } from './pages/CustomerDetailPage';
import { CustomerRecommendationPage } from './pages/CustomerRecommendationPage';
import { HairstyleDetailPage } from './pages/HairstyleDetailPage';
import { TrendReportPage } from './pages/TrendReportPage';

export const router = createBrowserRouter(
  [
    {
      path: '/',
      Component: AdminLoginPage,
    },
    {
      path: '/dashboard',
      Component: DashboardPage,
    },
    {
      path: '/index.html',
      Component: AdminLoginPage,
    },
    {
      path: '/customer-list',
      Component: CustomerListPage,
    },
    {
      path: '/customer-search',
      Component: CustomerSearchPage,
    },
    {
      path: '/customer/:id',
      Component: CustomerDetailPage,
    },
    {
      path: '/customer/:id/recommendation',
      Component: CustomerRecommendationPage,
    },
    {
      path: '/hairstyle/:id',
      Component: HairstyleDetailPage,
    },
    {
      path: '/trend-report',
      Component: TrendReportPage,
    },
    {
      path: '*',
      Component: AdminLoginPage,
    },
  ],
  {
    basename: '/admin',
  }
);
