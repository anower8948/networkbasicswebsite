import { motion } from 'motion/react';

import { cn } from '@/lib/cn';
import type { LevelProgress } from '@/types/api';

interface XPBarProps {
  level: LevelProgress;
  className?: string;
}

/**
 * Level and progress toward the next one.
 *
 * Every number here is computed server-side and simply rendered — the level
 * curve must have exactly one implementation.
 */
export function XPBar({ level, className }: XPBarProps) {
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-title text-sm font-semibold">
          Level {level.level}
          {level.isMaxLevel && (
            <span className="ml-2 text-[12px] font-normal text-[var(--text-tertiary)]">
              max
            </span>
          )}
        </span>
        <span className="text-[12px] text-[var(--text-tertiary)] tabular-nums">
          {level.isMaxLevel
            ? `${level.totalXp.toLocaleString()} XP`
            : `${level.xpIntoLevel.toLocaleString()} / ${level.xpForNextLevel.toLocaleString()} XP`}
        </span>
      </div>

      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(level.percentToNextLevel)}
        aria-label={`Level ${level.level} progress`}
        className="h-2 overflow-hidden rounded-full bg-[var(--surface-sunken)]"
      >
        <motion.div
          className="h-full rounded-full bg-linear-to-r from-accent-400 to-accent-600"
          initial={{ width: 0 }}
          animate={{ width: `${level.percentToNextLevel}%` }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>

      {!level.isMaxLevel && (
        <p className="text-[12px] text-[var(--text-tertiary)]">
          {(level.nextLevelXp - level.totalXp).toLocaleString()} XP to level {level.level + 1}
        </p>
      )}
    </div>
  );
}
