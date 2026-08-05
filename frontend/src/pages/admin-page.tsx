/**
 * Instructor and admin tooling.
 *
 * The two tables that earn their place are lab and quiz performance. A lab with
 * a low pass rate *and* a high hint average is not a hard lab, it is a badly
 * worded one — and the point of putting those columns side by side is to make
 * that visible at a glance.
 */

import { useQuery } from '@tanstack/react-query';
import { GraduationCap, TrendingUp, Users } from 'lucide-react';
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { adminApi } from '@/features/admin/api/admin-api';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { adminKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <GlassPanel radius="lg" className="p-4">
      <p className="text-[12px] text-[var(--text-tertiary)]">{label}</p>
      <p className="text-title mt-1 text-2xl font-semibold tabular-nums">
        {/* A figure the server did not send renders as a dash. These types are
            hand-written against the wire format, so a renamed field is a
            runtime mismatch the type-checker cannot see — and one missing
            number should not take the whole page down with it. */}
        {typeof value === 'number' ? value.toLocaleString() : '—'}
      </p>
    </GlassPanel>
  );
}

function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-[13px]">
        <thead>
          <tr className="hairline-b">
            {headers.map((header, index) => (
              <th
                key={header}
                className={cn(
                  'px-3 py-2 font-medium text-[var(--text-tertiary)]',
                  index > 0 && 'text-right',
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row[0])} className="hairline-b last:border-0">
              {row.map((cell, index) => (
                <td
                  key={index}
                  className={cn(
                    'px-3 py-2',
                    index > 0 && 'text-right tabular-nums',
                    index === 0 && 'font-medium',
                  )}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<'content' | 'roster'>('content');

  const analytics = useQuery({
    queryKey: adminKeys.analytics,
    queryFn: adminApi.analytics,
  });

  const roster = useQuery({
    queryKey: adminKeys.roster,
    queryFn: adminApi.roster,
    enabled: tab === 'roster',
  });

  // The route guard is server-side; this is only so the page says something
  // useful rather than flashing an error envelope.
  if (user && user.role === 'student') {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="warning" title="Instructors only">
          This area is for instructors and administrators.
        </Alert>
      </div>
    );
  }

  if (analytics.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading analytics" />
      </div>
    );
  }

  if (analytics.error || !analytics.data) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Could not load analytics">
          Please try again in a moment.
        </Alert>
      </div>
    );
  }

  const { overview, courses, labs, quizzes } = analytics.data;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-title text-2xl font-semibold">Instructor tools</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          How the content is performing, across everyone taking it.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Learners" value={overview.totalUsers} />
        <Stat label="Active this week" value={overview.activeUsersWeek} />
        <Stat label="Lessons completed" value={overview.lessonsCompleted} />
        <Stat label="Certificates issued" value={overview.certificatesIssued} />
      </div>

      <div role="tablist" aria-label="Admin sections" className="flex gap-1">
        {(['content', 'roster'] as const).map((item) => (
          <button
            key={item}
            role="tab"
            type="button"
            aria-selected={tab === item}
            onClick={() => setTab(item)}
            className={cn(
              'rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] font-medium capitalize',
              tab === item
                ? 'bg-accent-500/12 text-accent-600 dark:text-accent-300'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]',
            )}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === 'content' && (
        <div className="flex flex-col gap-6">
          <GlassPanel radius="xl" className="p-5">
            <h2 className="text-title flex items-center gap-2 text-base font-semibold">
              <GraduationCap className="size-4 text-accent-500" aria-hidden />
              Courses
            </h2>
            <div className="mt-3">
              <Table
                headers={['Course', 'Enrolled', 'Completed', 'Completion', 'Avg progress']}
                rows={courses.map((course) => [
                  course.title,
                  course.enrollments,
                  course.completions,
                  `${course.completionRate}%`,
                  `${course.averageProgress}%`,
                ])}
              />
            </div>
          </GlassPanel>

          <GlassPanel radius="xl" className="p-5">
            <h2 className="text-title flex items-center gap-2 text-base font-semibold">
              <TrendingUp className="size-4 text-accent-500" aria-hidden />
              Labs
            </h2>
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              A low pass rate beside a high hint average usually means the wording,
              not the difficulty.
            </p>
            <div className="mt-3">
              <Table
                headers={['Lab', 'Attempts', 'Passes', 'Pass rate', 'Avg score', 'Avg hints']}
                rows={labs.map((lab) => [
                  lab.title,
                  lab.attempts,
                  lab.passes,
                  `${lab.passRate}%`,
                  `${lab.averageScore}%`,
                  lab.averageHints,
                ])}
              />
            </div>
          </GlassPanel>

          <GlassPanel radius="xl" className="p-5">
            <h2 className="text-title text-base font-semibold">Quizzes</h2>
            <div className="mt-3">
              <Table
                headers={['Quiz', 'Attempts', 'Avg score', 'Pass rate']}
                rows={quizzes.map((quiz) => [
                  quiz.quizTitle,
                  quiz.attempts,
                  `${quiz.averageScore}%`,
                  `${quiz.passRate}%`,
                ])}
              />
            </div>
          </GlassPanel>
        </div>
      )}

      {tab === 'roster' && (
        <GlassPanel radius="xl" className="p-5">
          <h2 className="text-title flex items-center gap-2 text-base font-semibold">
            <Users className="size-4 text-accent-500" aria-hidden />
            Learners
          </h2>
          <div className="mt-3">
            {roster.isLoading ? (
              <div className="flex justify-center py-8">
                <Spinner className="text-accent-500" label="Loading roster" />
              </div>
            ) : (
              <Table
                headers={['Learner', 'Level', 'XP', 'Lessons', 'Labs', 'Last active']}
                rows={(roster.data ?? []).map((entry) => [
                  entry.displayName,
                  entry.level,
                  entry.totalXp,
                  entry.lessonsCompleted,
                  entry.labsCompleted,
                  entry.lastActiveAt
                    ? new Date(entry.lastActiveAt).toLocaleDateString()
                    : '—',
                ])}
              />
            )}
          </div>
        </GlassPanel>
      )}
    </div>
  );
}
