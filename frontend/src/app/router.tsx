import type { ComponentType } from 'react';
import { createBrowserRouter } from 'react-router';
import { GuestOnly, RequireRole } from '@/features/auth/guards';
import { AuthLayout } from '@/layouts/AuthLayout';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { PublicLayout } from '@/layouts/PublicLayout';
import { CheckEmailPage } from '@/pages/auth/CheckEmailPage';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage';
import { LandingPage } from '@/pages/public/LandingPage';
import { PersonalDataPolicyPage } from '@/pages/public/PersonalDataPolicyPage';
import { ForbiddenPage, NotFoundPage, RouteErrorPage } from '@/pages/public/StatusPages';

function page<T>(load: () => Promise<T>, pick: (module: T) => ComponentType) {
  // Страницы кабинетов грузятся отдельными чанками: лендингу и входу не нужны
  // подсветка кода, формы анкеты и таблицы методиста.
  return async () => ({ Component: pick(await load()) });
}

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <LandingPage /> },
      {
        path: 'design-system',
        lazy: page(
          () => import('@/pages/public/DesignSystemPage'),
          (module) => module.DesignSystemPage,
        ),
      },
      { path: 'legal/personal-data', element: <PersonalDataPolicyPage /> },
      { path: 'forbidden', element: <ForbiddenPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    path: 'auth',
    element: <AuthLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        path: 'login',
        element: (
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        ),
      },
      {
        path: 'register',
        element: (
          <GuestOnly>
            <RegisterPage />
          </GuestOnly>
        ),
      },
      { path: 'check-email', element: <CheckEmailPage /> },
      { path: 'verify', element: <VerifyEmailPage /> },
    ],
  },
  {
    path: 'c',
    element: (
      <RequireRole roles={['candidate']}>
        <CabinetLayout role="candidate" />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        lazy: page(
          () => import('@/pages/candidate/CandidateHomePage'),
          (module) => module.CandidateHomePage,
        ),
      },
      {
        path: 'onboarding',
        lazy: page(
          () => import('@/pages/candidate/OnboardingPage'),
          (module) => module.OnboardingPage,
        ),
      },
      {
        path: 'profile',
        lazy: page(
          () => import('@/pages/candidate/ProfilePage'),
          (module) => module.ProfilePage,
        ),
      },
      {
        path: 'assessment',
        lazy: page(
          () => import('@/pages/candidate/AssessmentPage'),
          (module) => module.AssessmentPage,
        ),
      },
      {
        path: 'assessment/sessions/:sessionId',
        lazy: page(
          () => import('@/pages/candidate/AssessmentSessionPage'),
          (module) => module.AssessmentSessionPage,
        ),
      },
      {
        path: 'settings',
        lazy: page(
          () => import('@/pages/candidate/SettingsPage'),
          (module) => module.SettingsPage,
        ),
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    path: 'e',
    element: (
      <RequireRole roles={['employer']}>
        <CabinetLayout role="employer" />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        lazy: page(
          () => import('@/pages/employer/EmployerHomePage'),
          (module) => module.EmployerHomePage,
        ),
      },
    ],
  },
  {
    path: 'm',
    element: (
      <RequireRole roles={['methodist']}>
        <CabinetLayout role="methodist" />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        lazy: page(
          () => import('@/pages/methodist/MethodistHomePage'),
          (module) => module.MethodistHomePage,
        ),
      },
    ],
  },
]);
