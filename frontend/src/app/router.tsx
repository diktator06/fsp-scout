import type { ComponentType } from 'react';
import { createBrowserRouter } from 'react-router';
import { GuestOnly, RequireRole } from '@/features/auth/guards';
import { AuthLayout } from '@/layouts/AuthLayout';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { PublicLayout } from '@/layouts/PublicLayout';
import { CheckEmailPage } from '@/pages/auth/CheckEmailPage';
import { FspLoginCallbackPage } from '@/pages/auth/FspLoginCallbackPage';
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
      { path: 'fsp/callback', element: <FspLoginCallbackPage /> },
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
        path: 'fsp',
        lazy: page(
          () => import('@/pages/candidate/FspPage'),
          (module) => module.FspPage,
        ),
      },
      {
        path: 'fsp/callback',
        lazy: page(
          () => import('@/pages/candidate/FspCallbackPage'),
          (module) => module.FspCallbackPage,
        ),
      },
      {
        path: 'settings',
        lazy: page(
          () => import('@/pages/candidate/SettingsPage'),
          (module) => module.SettingsPage,
        ),
      },
      {
        path: 'vacancies',
        lazy: page(
          () => import('@/pages/candidate/VacanciesPage'),
          (module) => module.VacanciesPage,
        ),
      },
      {
        path: 'vacancies/:vacancyId',
        lazy: page(
          () => import('@/pages/candidate/VacancyPage'),
          (module) => module.VacancyPage,
        ),
      },
      {
        path: 'tasks',
        lazy: page(
          () => import('@/pages/candidate/TasksPage'),
          (module) => module.TasksPage,
        ),
      },
      {
        path: 'applications',
        lazy: page(
          () => import('@/pages/candidate/ApplicationsPage'),
          (module) => module.ApplicationsPage,
        ),
      },
      {
        path: 'invitations',
        lazy: page(
          () => import('@/pages/candidate/InvitationsPage'),
          (module) => module.CandidateInvitationsPage,
        ),
      },
      {
        path: 'invitations/:invitationId',
        lazy: page(
          () => import('@/pages/candidate/InvitationPage'),
          (module) => module.CandidateInvitationPage,
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
      {
        path: 'company',
        lazy: page(
          () => import('@/pages/employer/CompanyPage'),
          (module) => module.CompanyPage,
        ),
      },
      {
        path: 'needs',
        lazy: page(
          () => import('@/pages/employer/NeedsPage'),
          (module) => module.NeedsPage,
        ),
      },
      {
        path: 'needs/new',
        lazy: page(
          () => import('@/pages/employer/NewNeedPage'),
          (module) => module.NewNeedPage,
        ),
      },
      {
        path: 'needs/:needId',
        lazy: page(
          () => import('@/pages/employer/NeedPage'),
          (module) => module.NeedPage,
        ),
      },
      {
        path: 'needs/:needId/edit',
        lazy: page(
          () => import('@/pages/employer/EditNeedPage'),
          (module) => module.EditNeedPage,
        ),
      },
      {
        path: 'bank',
        lazy: page(
          () => import('@/pages/employer/BankPage'),
          (module) => module.BankPage,
        ),
      },
      {
        path: 'candidates/:candidateId',
        lazy: page(
          () => import('@/pages/employer/CandidatePage'),
          (module) => module.CandidatePage,
        ),
      },
      {
        path: 'tasks',
        lazy: page(
          () => import('@/pages/employer/TasksPage'),
          (module) => module.EmployerTasksPage,
        ),
      },
      {
        path: 'tasks/:taskId',
        lazy: page(
          () => import('@/pages/employer/TaskPage'),
          (module) => module.EmployerTaskPage,
        ),
      },
      {
        path: 'vacancies',
        lazy: page(
          () => import('@/pages/employer/VacanciesPage'),
          (module) => module.EmployerVacanciesPage,
        ),
      },
      {
        path: 'vacancies/new',
        lazy: page(
          () => import('@/pages/employer/VacancyFormPage'),
          (module) => module.VacancyFormPage,
        ),
      },
      {
        path: 'vacancies/:vacancyId',
        lazy: page(
          () => import('@/pages/employer/VacancyPage'),
          (module) => module.EmployerVacancyPage,
        ),
      },
      {
        path: 'vacancies/:vacancyId/edit',
        lazy: page(
          () => import('@/pages/employer/VacancyFormPage'),
          (module) => module.VacancyFormPage,
        ),
      },
      {
        path: 'integrations',
        lazy: page(
          () => import('@/pages/employer/IntegrationsPage'),
          (module) => module.IntegrationsPage,
        ),
      },
      {
        path: 'invitations',
        lazy: page(
          () => import('@/pages/employer/InvitationsPage'),
          (module) => module.InvitationsPage,
        ),
      },
      {
        path: 'invitations/:invitationId',
        lazy: page(
          () => import('@/pages/employer/InvitationsPage'),
          (module) => module.InvitationsPage,
        ),
      },
      { path: '*', element: <NotFoundPage /> },
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
      {
        path: 'moderation',
        lazy: page(
          () => import('@/pages/methodist/ModerationPage'),
          (module) => module.ModerationPage,
        ),
      },
      {
        path: 'item-bank',
        lazy: page(
          () => import('@/pages/methodist/ItemBankPage'),
          (module) => module.ItemBankPage,
        ),
      },
      {
        path: 'vacancy-test',
        lazy: page(
          () => import('@/pages/methodist/VacancyTestPage'),
          (module) => module.VacancyTestPage,
        ),
      },
      {
        path: 'settings',
        lazy: page(
          () => import('@/pages/methodist/AssessmentSettingsPage'),
          (module) => module.AssessmentSettingsPage,
        ),
      },
    ],
  },
]);
