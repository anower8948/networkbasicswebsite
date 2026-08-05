import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { FullPageSpinner } from '@/components/ui/spinner';
import { useAuth } from '@/features/auth/hooks/use-auth';
import type { UserRole } from '@/types/api';

const ROLE_RANK: Record<UserRole, number> = { student: 0, instructor: 1, admin: 2 };

interface ProtectedRouteProps {
  /** Minimum role required. A higher role always satisfies a lower one. */
  minimumRole?: UserRole;
}

/**
 * Route guard for authenticated areas.
 *
 * This is a *usability* control, not a security boundary — it decides what to
 * render, while the API independently authorises every request. A user who
 * edits their client state gains a broken screen, not data.
 */
export function ProtectedRoute({ minimumRole = 'student' }: ProtectedRouteProps) {
  const { isAuthenticated, isInitialising, user } = useAuth();
  const location = useLocation();

  // Waiting on the initial silent refresh — redirecting now would sign out
  // every user who reloads the page.
  if (isInitialising) {
    return <FullPageSpinner label="Restoring your session" />;
  }

  if (!isAuthenticated || !user) {
    // `state.from` lets the login page send the user back where they were.
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (ROLE_RANK[user.role] < ROLE_RANK[minimumRole]) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}

/** Inverse guard: keeps signed-in users off the login and registration pages. */
export function PublicOnlyRoute() {
  const { isAuthenticated, isInitialising } = useAuth();

  if (isInitialising) {
    return <FullPageSpinner label="Restoring your session" />;
  }

  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <Outlet />;
}
