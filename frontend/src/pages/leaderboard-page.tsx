/**
 * The leaderboard.
 *
 * Your own row is pinned below the table when you are outside the top 50, so
 * the page says something to everyone rather than only to the fifty people who
 * least need the encouragement.
 */

import { useQuery } from '@tanstack/react-query';
import { Medal } from 'lucide-react';
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Avatar } from '@/components/ui/avatar';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { gamificationApi } from '@/features/gamification/api/gamification-api';
import { gamificationKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';
import { SCOPE_LABELS, type LeaderboardEntry, type LeaderboardScope } from '@/types/gamification';

const SCOPES: LeaderboardScope[] = ['all_time', 'monthly', 'weekly'];

const MEDAL_COLORS: Record<number, string> = {
  1: 'oklch(0.78 0.14 85)',
  2: 'oklch(0.75 0.02 250)',
  3: 'oklch(0.65 0.10 55)',
};

function Row({ entry, showRank = true }: { entry: LeaderboardEntry; showRank?: boolean }) {
  const medal = MEDAL_COLORS[entry.rank];

  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5',
        entry.isYou && 'bg-accent-500/10 ring-1 ring-accent-500/30',
      )}
    >
      <span className="flex w-8 shrink-0 justify-center">
        {showRank && entry.rank > 0 ? (
          medal ? (
            <Medal className="size-4" style={{ color: medal }} aria-hidden />
          ) : (
            <span className="text-[13px] tabular-nums text-[var(--text-tertiary)]">
              {entry.rank}
            </span>
          )
        ) : (
          <span className="text-[13px] text-[var(--text-tertiary)]">—</span>
        )}
      </span>

      <Avatar name={entry.displayName} imageUrl={entry.avatarUrl} size="sm" />

      <span className="min-w-0 flex-1 truncate text-[14px] font-medium">
        {entry.displayName}
        {entry.isYou && (
          <span className="ml-2 text-[11px] font-normal text-accent-500">You</span>
        )}
      </span>

      <span className="shrink-0 text-[12px] text-[var(--text-tertiary)]">
        Level {entry.level}
      </span>
      <span className="w-20 shrink-0 text-right text-[14px] font-semibold tabular-nums">
        {entry.xp.toLocaleString()}
      </span>
    </li>
  );
}

export default function LeaderboardPage() {
  const [scope, setScope] = useState<LeaderboardScope>('all_time');

  const { data, isLoading, error } = useQuery({
    queryKey: gamificationKeys.leaderboard(scope),
    queryFn: () => gamificationApi.leaderboard(scope),
  });

  // Only pin your own row when it is not already in the table above.
  const youAreListed = data?.entries.some((entry) => entry.isYou) ?? false;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-title text-2xl font-semibold">Leaderboard</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Ranked by experience earned.
        </p>
      </header>

      <div role="tablist" aria-label="Leaderboard period" className="flex gap-1">
        {SCOPES.map((item) => (
          <button
            key={item}
            role="tab"
            type="button"
            aria-selected={scope === item}
            onClick={() => setScope(item)}
            className={cn(
              'rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] font-medium',
              'transition-all duration-[var(--duration-fast)]',
              scope === item
                ? 'bg-accent-500/12 text-accent-600 dark:text-accent-300'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]',
            )}
          >
            {SCOPE_LABELS[item]}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" className="text-accent-500" label="Loading leaderboard" />
        </div>
      )}

      {error && (
        <Alert tone="danger" title="Could not load the leaderboard">
          Please try again in a moment.
        </Alert>
      )}

      {data && (
        <>
          <GlassPanel radius="xl" className="p-2">
            {data.entries.length === 0 ? (
              <p className="px-3 py-8 text-center text-[13px] text-[var(--text-tertiary)]">
                Nobody has earned any experience in this period yet.
              </p>
            ) : (
              <ol className="flex flex-col gap-0.5">
                {data.entries.map((entry) => (
                  <Row key={entry.userId} entry={entry} />
                ))}
              </ol>
            )}
          </GlassPanel>

          {data.you && !youAreListed && (
            <div>
              <p className="mb-1.5 text-[12px] text-[var(--text-tertiary)]">Your standing</p>
              <GlassPanel radius="xl" className="p-2">
                <ol>
                  <Row entry={data.you} showRank={scope === 'all_time'} />
                </ol>
              </GlassPanel>
              {scope !== 'all_time' && (
                <p className="mt-1.5 text-[12px] text-[var(--text-tertiary)]">
                  Ranks outside the top {data.entries.length} are only counted on the
                  all-time board.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
