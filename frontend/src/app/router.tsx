import { createBrowserRouter } from 'react-router';
import { GuestOnly, RequireRole } from '@/features/auth/guards';
import { AuthLayout } from '@/layouts/AuthLayout';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { PublicLayout } from '@/layouts/PublicLayout';
import { CheckEmailPage } from '@/pages/auth/CheckEmailPage';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage';
import { CandidateHomePage } from '@/pages/candidate/CandidateHomePage';
import { EmployerHomePage } from '@/pages/employer/EmployerHomePage';
import { MethodistHomePage } from '@/pages/methodist/MethodistHomePage';
import { DesignSystemPage } from '@/pages/public/DesignSystemPage';
import { LandingPage } from '@/pages/public/LandingPage';
import { PersonalDataPolicyPage } from '@/pages/public/PersonalDataPolicyPage';
import { ForbiddenPage, NotFoundPage, RouteErrorPage } from '@/pages/public/StatusPages';

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: 'design-system', element: <DesignSystemPage /> },
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
    children: [{ index: true, element: <CandidateHomePage /> }],
  },
  {
    path: 'e',
    element: (
      <RequireRole roles={['employer']}>
        <CabinetLayout role="employer" />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [{ index: true, element: <EmployerHomePage /> }],
  },
  {
    path: 'm',
    element: (
      <RequireRole roles={['methodist']}>
        <CabinetLayout role="methodist" />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [{ index: true, element: <MethodistHomePage /> }],
  },
]);
