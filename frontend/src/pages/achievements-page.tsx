/**
 * The trophy case.
 *
 * Unearned badges show a progress bar rather than just a grey outline, because
 * "3 of 10 labs" is an invitation and a locked padlock is not. Secret badges
 * are absent entirely until earned — the server never sends them, so there is
 * nothing here to reveal them.
 */

import { useQuery } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Lock, Trophy } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { gamificationApi } from '@/features/gamification/api/gamification-api';
import { gamificationKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';
import {
  CATEGORY_LABELS,
  type Achievement,
  type AchievementCategory,
} from '@/types/gamification';

const CATEGORY_ORDER: AchievementCategory[] = [
  'progress',
  'lab',
  'mastery',
  'streak',
  'community',
  'special',
];

function BadgeCard({ achievement }: { achievement: Achievement }) {
  const { earned, progressPercent } = achievement;

  return (
    <GlassPanel
      radius="lg"
      className={cn(
        'flex gap-3 p-4 transition-opacity',
        !earned && 'opacity-75',
      )}
    >
      <span
        className={cn(
          'flex size-10 shrink-0 items-center justify-center rounded-full',
          earned
            ? 'bg-accent-500/15 text-accent-500'
            : 'bg-[var(--surface-sunken)] text-[var(--text-tertiary)]',
        )}
      >
        {earned ? (
          <Trophy className="size-5" aria-hidden />
        ) : (
          <Lock className="size-4" aria-hidden />
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-title text-[14px] font-semibold">{achievement.title}</h3>
          {achievement.xpReward > 0 && (
            <span className="shrink-0 text-[11px] font-medium text-accent-500">
              +{achievement.xpReward} XP
            </span>
          )}
        </div>

        <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">
          {achievement.description}
        </p>

        {earned ? (
          <p className="mt-1.5 text-[11px] text-[var(--color-success)]">
            Earned
            {achievement.earnedAt &&
              ` ${new Date(achievement.earnedAt).toLocaleDateString()}`}
          </p>
        ) : (
          progressPercent !== null && (
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-sunken)]">
                <div
                  className="h-full rounded-full bg-accent-500 transition-[width] duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="shrink-0 text-[11px] tabular-nums text-[var(--text-tertiary)]">
                {Math.round(progressPercent)}%
              </span>
            </div>
          )
        )}
      </div>
    </GlassPanel>
  );
}

export default function AchievementsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: gamificationKeys.achievements,
    queryFn: gamificationApi.achievements,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading achievements" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Could not load your achievements">
          Please try again in a moment.
        </Alert>
      </div>
    );
  }

  const groups = CATEGORY_ORDER.map((category) => ({
    category,
    items: data.items.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-title text-2xl font-semibold">Achievements</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          {data.earnedCount} of {data.totalCount} earned.
        </p>
        <div className="mt-3 h-2 max-w-md overflow-hidden rounded-full bg-[var(--surface-sunken)]">
          <div
            className="h-full rounded-full bg-accent-500 transition-[width] duration-700"
            style={{
              width: `${data.totalCount ? (data.earnedCount / data.totalCount) * 100 : 0}%`,
            }}
          />
        </div>
      </header>

      {groups.map((group, index) => (
        <motion.section
          key={group.category}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.05 }}
          className="flex flex-col gap-3"
        >
          <h2 className="text-title text-lg font-semibold">
            {CATEGORY_LABELS[group.category]}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.items.map((achievement) => (
              <BadgeCard key={achievement.id} achievement={achievement} />
            ))}
          </div>
        </motion.section>
      ))}
    </div>
  );
}
