/**
 * The learner's landing page.
 *
 * Reads live progress from `/users/me/progress` — XP, level, streaks and a
 * recent-activity feed. Parts 3 and 8 replace the placeholder track cards with
 * real enrolments and resume links.
 */

import { motion } from 'motion/react';
import { ArrowRight, BookOpen, Clock, Flame, GraduationCap, Trophy, Zap } from 'lucide-react';

import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { XPBar } from '@/components/ui/xp-bar';
import { VerificationBanner } from '@/features/auth/components/verification-banner';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { useProgress } from '@/features/profile/hooks/use-progress';
import { useEnrollments } from '@/features/learning/hooks/use-catalog';
import type { XPReason, XPTransaction } from '@/types/api';

const XP_REASON_LABELS: Record<XPReason, string> = {
  lesson_completed: 'Lesson completed',
  quiz_passed: 'Quiz passed',
  lab_completed: 'Lab completed',
  course_completed: 'Course completed',
  achievement_earned: 'Achievement earned',
  streak_bonus: 'Streak bonus',
  manual_adjustment: 'Adjustment',
};

/** Pluralise a count: 1 day, 2 days. */
function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function formatStudyTime(seconds: number): string {
  if (seconds < 60) return '0m';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function ActivityFeed({ entries }: { entries: XPTransaction[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-[13px] text-[var(--text-secondary)]">
        No activity yet. Completing lessons and labs will show up here.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-[var(--hairline)]">
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-center justify-between gap-3 py-2.5">
          <span className="text-[13px]">{XP_REASON_LABELS[entry.reason]}</span>
          <span className="flex items-center gap-3">
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {new Date(entry.createdAt).toLocaleDateString()}
            </span>
            <span className="text-[13px] font-medium text-accent-600 tabular-nums dark:text-accent-400">
              +{entry.amount}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Courses the learner has started, or a prompt to browse the catalogue. */
function ContinueLearning() {
  const { data: enrollments, isLoading } = useEnrollments();

  if (isLoading) return null;

  if (!enrollments || enrollments.length === 0) {
    return (
      <section aria-label="Start learning" className="flex flex-col gap-4">
        <h2 className="text-title text-lg font-semibold">Start learning</h2>
        <GlassPanel radius="xl" className="flex flex-wrap items-center justify-between gap-3 p-6">
          <div>
            <p className="text-[15px] font-medium">You have not enrolled in a course yet</p>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              Begin with the Foundations track — OSI, TCP/IP, addressing and subnetting.
            </p>
          </div>
          <Link
            to="/courses"
            className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-sm)] bg-accent-500 px-5 text-sm font-medium text-white transition-colors hover:bg-accent-600"
          >
            Browse courses
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </GlassPanel>
      </section>
    );
  }

  return (
    <section aria-label="Continue learning" className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-title text-lg font-semibold">Continue learning</h2>
        <Link
          to="/courses"
          className="text-[13px] text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
        >
          All courses
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {enrollments.map((enrollment) => (
          <Link key={enrollment.id} to={`/courses/${enrollment.course.slug}`} className="block">
            <GlassPanel radius="xl" interactive className="flex h-full flex-col gap-3 p-5">
              <h3 className="text-title text-[15px] font-semibold">{enrollment.course.title}</h3>
              <div className="flex flex-col gap-1.5">
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-sunken)]">
                  <div
                    className="h-full rounded-full bg-linear-to-r from-accent-400 to-accent-600 transition-[width] duration-500"
                    style={{ width: `${enrollment.progressPercent}%` }}
                  />
                </div>
                <span className="text-[12px] text-[var(--text-tertiary)]">
                  {enrollment.progressPercent}% complete
                </span>
              </div>
              <div className="mt-auto flex items-center gap-4 text-[12px] text-[var(--text-tertiary)]">
                <span className="flex items-center gap-1.5">
                  <BookOpen className="size-3.5" aria-hidden />
                  {enrollment.course.lessonCount} lessons
                </span>
                {enrollment.status === 'completed' && (
                  <span className="text-[var(--color-success)]">Completed</span>
                )}
              </div>
            </GlassPanel>
          </Link>
        ))}
      </div>
    </section>
  );
}


export default function DashboardPage() {
  const { user } = useAuth();
  const { data: progress, isLoading, error } = useProgress();

  const greetingName = user?.fullName?.split(' ')[0] ?? user?.username ?? 'there';

  const cards = [
    {
      label: 'Experience',
      value: `${(progress?.totalXp ?? 0).toLocaleString()} XP`,
      Icon: Zap,
      tone: 'var(--color-accent-500)',
    },
    {
      label: 'Lessons completed',
      value: String(progress?.lessonsCompleted ?? 0),
      Icon: GraduationCap,
      tone: 'var(--color-track-foundation)',
    },
    {
      label: 'Labs completed',
      value: String(progress?.labsCompleted ?? 0),
      Icon: Trophy,
      tone: 'var(--color-track-intermediate)',
    },
    {
      label: 'Current streak',
      value: plural(progress?.currentStreakDays ?? 0, 'day'),
      Icon: Flame,
      tone: 'var(--color-warning)',
    },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <h1 className="text-display text-[28px] leading-tight font-semibold">
          Welcome back, {greetingName}
        </h1>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          {progress && progress.totalXp > 0
            ? `Level ${progress.level.level} · ${formatStudyTime(progress.totalStudySeconds)} studied · ${progress.xpThisWeek} XP this week`
            : 'Your learning journey starts here. Pick a track below to begin.'}
        </p>
      </motion.header>

      <VerificationBanner />

      {error && <Alert tone="danger">Could not load your progress. Try reloading the page.</Alert>}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" className="text-accent-500" label="Loading your progress" />
        </div>
      ) : (
        <>
          <section aria-label="Your statistics">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {cards.map(({ label, value, Icon, tone }, index) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
                >
                  <GlassPanel radius="lg" interactive className="flex flex-col gap-3 p-5">
                    <span
                      className="flex size-9 items-center justify-center rounded-[var(--radius-sm)]"
                      style={{ backgroundColor: `color-mix(in oklab, ${tone} 16%, transparent)` }}
                    >
                      <Icon className="size-[18px]" style={{ color: tone }} aria-hidden />
                    </span>
                    <div>
                      <p className="text-title text-2xl font-semibold">{value}</p>
                      <p className="mt-0.5 text-[13px] text-[var(--text-secondary)]">{label}</p>
                    </div>
                  </GlassPanel>
                </motion.div>
              ))}
            </div>
          </section>

          {progress && (
            <section aria-label="Level and activity" className="grid gap-4 lg:grid-cols-3">
              <motion.div
                className="lg:col-span-2"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
              >
                <GlassPanel radius="xl" className="flex h-full flex-col gap-5 p-6">
                  <XPBar level={progress.level} />
                  <div className="hairline-t flex flex-wrap gap-x-8 gap-y-3 pt-5">
                    <div>
                      <p className="text-[12px] text-[var(--text-tertiary)]">Longest streak</p>
                      <p className="text-title text-lg font-semibold">
                        {plural(progress.longestStreakDays, 'day')}
                      </p>
                    </div>
                    <div>
                      <p className="text-[12px] text-[var(--text-tertiary)]">Quizzes passed</p>
                      <p className="text-title text-lg font-semibold">
                        {progress.quizzesPassed}
                      </p>
                    </div>
                    <div>
                      <p className="text-[12px] text-[var(--text-tertiary)]">Study time</p>
                      <p className="text-title text-lg font-semibold">
                        {formatStudyTime(progress.totalStudySeconds)}
                      </p>
                    </div>
                  </div>
                </GlassPanel>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
              >
                <GlassPanel radius="xl" className="flex h-full flex-col p-6">
                  <h2 className="text-title flex items-center gap-2 text-base font-semibold">
                    <Clock className="size-4 text-[var(--text-tertiary)]" aria-hidden />
                    Recent activity
                  </h2>
                  <div className="mt-4">
                    <ActivityFeed entries={progress.recentXp} />
                  </div>
                </GlassPanel>
              </motion.div>
            </section>
          )}
        </>
      )}

      <ContinueLearning />
    </div>
  );
}
