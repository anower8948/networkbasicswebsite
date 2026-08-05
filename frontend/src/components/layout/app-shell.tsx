/**
 * The authenticated application chrome: a translucent sidebar, a floating
 * toolbar, and the routed content area.
 *
 * The sidebar is fixed and the content scrolls beneath the toolbar, so the
 * blur has moving content to refract — the effect that makes the glass read as
 * a real material rather than a static tint.
 */

import { motion } from 'motion/react';
import {
  Award,
  BarChart3,
  BookOpen,
  ClipboardList,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  NotebookPen,
  Settings,
  Trophy,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';

import { Avatar } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { FullPageSpinner } from '@/components/ui/spinner';
import { Wordmark } from '@/components/ui/logo';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { cn } from '@/lib/cn';

interface NavItem {
  to: string;
  label: string;
  Icon: typeof LayoutDashboard;
  /** Readable without an account, like the catalogue itself. */
  isPublic?: boolean;
  /** Instructor tooling — hidden from students rather than shown and refused. */
  staffOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/courses', label: 'Courses', Icon: BookOpen, isPublic: true },
  { to: '/simulator', label: 'Simulator', Icon: Network },
  { to: '/labs', label: 'Labs', Icon: FlaskConical, isPublic: true },
  { to: '/notes', label: 'Notes', Icon: NotebookPen },
  { to: '/achievements', label: 'Achievements', Icon: Trophy },
  { to: '/leaderboard', label: 'Leaderboard', Icon: BarChart3 },
  { to: '/certificates', label: 'Certificates', Icon: Award },
  { to: '/admin', label: 'Instructor', Icon: ClipboardList, staffOnly: true },
  { to: '/settings', label: 'Settings', Icon: Settings },
];

function SidebarContent({
  onNavigate,
  isAuthenticated,
  isStaff,
}: {
  onNavigate?: () => void;
  isAuthenticated: boolean;
  isStaff: boolean;
}) {
  // Anonymous visitors see only what they can actually use: the rest would be
  // shown and then bounced by the route guard. Instructor tooling is hidden
  // from students for the same reason — the server refuses it either way.
  const items = NAV_ITEMS.filter((item) => {
    if (!isAuthenticated) return item.isPublic === true;
    return !item.staffOnly || isStaff;
  });

  return (
    <nav className="flex flex-1 flex-col gap-1 px-3" aria-label="Main">
      {items.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5 text-sm font-medium',
              'transition-all duration-[var(--duration-fast)]',
              isActive
                ? 'bg-accent-500/12 text-accent-600 dark:text-accent-300'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text-primary)]',
            )
          }
        >
          <Icon className="size-[18px] shrink-0" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell() {
  const { user, logout, isAuthenticated, isInitialising } = useAuth();
  const navigate = useNavigate();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  const isStaff = user?.role === 'instructor' || user?.role === 'admin';

  const handleLogout = async () => {
    await logout();
    void navigate('/login', { replace: true });
  };

  // Auth resolves via one silent refresh on mount; rendering before it
  // settles would flash a "Sign in" button at an authenticated learner.
  if (isInitialising) {
    return <FullPageSpinner label="Loading" />;
  }

  return (
    <div className="flex min-h-dvh">
      {/* Desktop sidebar */}
      <aside className="glass-thin fixed inset-y-0 left-0 z-30 hidden w-64 flex-col py-5 lg:flex">
        <div className="px-5 pb-6">
          <Wordmark />
        </div>
        <SidebarContent isAuthenticated={isAuthenticated} isStaff={isStaff} />
        {isAuthenticated && (
          <div className="hairline-t mx-3 mt-3 pt-3">
            <Button
              variant="ghost"
              size="sm"
              fullWidth
              leadingIcon={<LogOut className="size-4" />}
              onClick={() => void handleLogout()}
              className="justify-start"
            >
              Sign out
            </Button>
          </div>
        )}
      </aside>

      {/* Mobile drawer */}
      {isMobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setIsMobileNavOpen(false)}
            className="absolute inset-0 bg-black/25 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="glass-strong absolute inset-y-0 left-0 flex w-64 flex-col py-5"
          >
            <div className="flex items-center justify-between px-5 pb-6">
              <Wordmark />
              <button
                type="button"
                aria-label="Close navigation"
                onClick={() => setIsMobileNavOpen(false)}
                className="rounded-[var(--radius-xs)] p-1 text-[var(--text-tertiary)]"
              >
                <X className="size-5" />
              </button>
            </div>
            <SidebarContent
              onNavigate={() => setIsMobileNavOpen(false)}
              isAuthenticated={isAuthenticated}
              isStaff={isStaff}
            />
          </motion.aside>
        </div>
      )}

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <GlassPanel
          as="header"
          material="thin"
          radius="sm"
          className="sticky top-0 z-20 flex items-center justify-between gap-3 rounded-none border-x-0 border-t-0 px-4 py-3 sm:px-6"
        >
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setIsMobileNavOpen(true)}
            className="rounded-[var(--radius-xs)] p-1.5 text-[var(--text-secondary)] lg:hidden"
          >
            <Menu className="size-5" />
          </button>

          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            {isAuthenticated ? (
              <Link
                to="/settings"
                className="flex items-center gap-2.5 rounded-[var(--radius-sm)] pl-1 transition-opacity hover:opacity-80"
                aria-label="Account settings"
              >
                <div className="hidden text-right sm:block">
                  <p className="text-[13px] leading-tight font-medium">
                    {user?.fullName ?? user?.username}
                  </p>
                  <p className="text-[12px] leading-tight text-[var(--text-tertiary)] capitalize">
                    {user?.role}
                  </p>
                </div>
                <Avatar
                  name={user?.fullName ?? user?.username ?? ''}
                  imageUrl={user?.avatarUrl}
                  size="md"
                />
              </Link>
            ) : (
              <Link
                to="/login"
                className="inline-flex h-9 items-center rounded-[var(--radius-sm)] bg-accent-500 px-4 text-[13px] font-medium text-white transition-colors hover:bg-accent-600"
              >
                Sign in
              </Link>
            )}
          </div>
        </GlassPanel>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
