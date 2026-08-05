/**
 * Route table.
 *
 * Pages are lazily imported so the login screen does not download the
 * authenticated application shell. As Parts 3–9 add the course viewer,
 * simulator and lab runner — each pulling in heavy dependencies like React Flow
 * and Konva — code splitting at the route boundary is what keeps first paint
 * fast.
 */

import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';

import { AppShell } from '@/components/layout/app-shell';
import { FullPageSpinner } from '@/components/ui/spinner';
import { ProtectedRoute, PublicOnlyRoute } from '@/features/auth/components/protected-route';

const LoginPage = lazy(() => import('@/pages/login-page'));
const RegisterPage = lazy(() => import('@/pages/register-page'));
const ForgotPasswordPage = lazy(() => import('@/pages/forgot-password-page'));
const ResetPasswordPage = lazy(() => import('@/pages/reset-password-page'));
const VerifyEmailPage = lazy(() => import('@/pages/verify-email-page'));
const DashboardPage = lazy(() => import('@/pages/dashboard-page'));
const CoursesPage = lazy(() => import('@/pages/courses-page'));
const CourseDetailPage = lazy(() => import('@/pages/course-detail-page'));
const LessonPage = lazy(() => import('@/pages/lesson-page'));
const TopologiesPage = lazy(() => import('@/pages/topologies-page'));
const SimulatorPage = lazy(() => import('@/pages/simulator-page'));
const LabsPage = lazy(() => import('@/pages/labs-page'));
const LabPage = lazy(() => import('@/pages/lab-page'));
const AchievementsPage = lazy(() => import('@/pages/achievements-page'));
const LeaderboardPage = lazy(() => import('@/pages/leaderboard-page'));
const CertificatesPage = lazy(() => import('@/pages/certificates-page'));
const VerifyCertificatePage = lazy(() => import('@/pages/verify-certificate-page'));
const NotesPage = lazy(() => import('@/pages/notes-page'));
const AdminPage = lazy(() => import('@/pages/admin-page'));
const SettingsPage = lazy(() => import('@/pages/settings-page'));
const NotFoundPage = lazy(() => import('@/pages/not-found-page'));

function withSuspense(node: React.ReactNode) {
  return <Suspense fallback={<FullPageSpinner />}>{node}</Suspense>;
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/dashboard" replace />,
  },
  // Landing pages for emailed links are reachable signed in *or* out. The link
  // is opened from a mail client in whatever browser the user happens to have,
  // and being already signed in elsewhere is common — bouncing an authenticated
  // visitor to the dashboard would silently swallow the action they came to do.
  {
    path: '/verify-email',
    element: withSuspense(<VerifyEmailPage />),
  },
  {
    path: '/reset-password',
    element: withSuspense(<ResetPasswordPage />),
  },
  // Certificate verification is reached from a link on someone's CV, by a
  // stranger with no account. It renders standalone — no shell, no navigation,
  // no sign-in prompt — because the whole page answers one question.
  {
    path: '/verify',
    element: withSuspense(<VerifyCertificatePage />),
  },
  {
    path: '/verify/:code',
    element: withSuspense(<VerifyCertificatePage />),
  },
  {
    element: <PublicOnlyRoute />,
    children: [
      { path: '/login', element: withSuspense(<LoginPage />) },
      { path: '/register', element: withSuspense(<RegisterPage />) },
      // Requesting a reset stays public-only: a signed-in user changes their
      // password in settings instead.
      { path: '/forgot-password', element: withSuspense(<ForgotPasswordPage />) },
    ],
  },
  {
    // The catalogue is browsable without an account — the API serves it
    // publicly, and letting someone read a lesson before signing up is the
    // point. These sit inside the app shell but outside the auth guard; the
    // shell renders a "Sign in" action instead of a profile when anonymous.
    element: <AppShell />,
    children: [
      { path: '/courses', element: withSuspense(<CoursesPage />) },
      { path: '/courses/:courseSlug', element: withSuspense(<CourseDetailPage />) },
      { path: '/courses/:courseSlug/:lessonSlug', element: withSuspense(<LessonPage />) },
      // The lab library is browsable anonymously for the same reason as the
      // catalogue; opening a lab needs an account, which the page's attempt
      // request enforces.
      { path: '/labs', element: withSuspense(<LabsPage />) },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/dashboard', element: withSuspense(<DashboardPage />) },
          { path: '/settings', element: withSuspense(<SettingsPage />) },
          { path: '/simulator', element: withSuspense(<TopologiesPage />) },
          // `new` is matched by the same route; the page treats a missing id
          // as an unsaved topology.
          { path: '/simulator/new', element: withSuspense(<SimulatorPage />) },
          { path: '/simulator/:topologyId', element: withSuspense(<SimulatorPage />) },
          { path: '/labs/:slug', element: withSuspense(<LabPage />) },
          { path: '/achievements', element: withSuspense(<AchievementsPage />) },
          { path: '/leaderboard', element: withSuspense(<LeaderboardPage />) },
          { path: '/certificates', element: withSuspense(<CertificatesPage />) },
          { path: '/notes', element: withSuspense(<NotesPage />) },
          // Guarded server-side by role; the page itself explains rather than
          // flashing a 403 envelope if a student reaches it.
          { path: '/admin', element: withSuspense(<AdminPage />) },
        ],
      },
    ],
  },
  { path: '*', element: withSuspense(<NotFoundPage />) },
]);
