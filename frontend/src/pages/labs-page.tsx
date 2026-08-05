/**
 * The lab library.
 *
 * Grouped by kind rather than by difficulty, because what a lab *asks of you*
 * changes how you approach it more than how hard it is: a troubleshooting lab
 * and a design lab of the same difficulty are different exercises.
 */

import { useQuery } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Check, Clock, FlaskConical, Target, Wrench, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { labApi } from '@/features/labs/api/lab-api';
import { labKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';
import {
  LAB_KIND_BLURBS,
  LAB_KIND_LABELS,
  type Difficulty,
  type LabKind,
  type LabSummary,
} from '@/types/lab';

const KIND_ORDER: LabKind[] = ['guided', 'challenge', 'troubleshooting', 'design'];

const KIND_ICONS: Record<LabKind, typeof FlaskConical> = {
  guided: FlaskConical,
  challenge: Target,
  troubleshooting: Wrench,
  design: Zap,
};

const DIFFICULTY_COLORS: Record<Difficulty, string> = {
  beginner: 'var(--color-track-foundation)',
  intermediate: 'var(--color-track-intermediate)',
  advanced: 'var(--color-track-advanced)',
  expert: 'var(--color-danger)',
};

function LabCard({ lab }: { lab: LabSummary }) {
  const color = DIFFICULTY_COLORS[lab.difficulty];
  const passed = lab.status === 'passed';

  return (
    <Link to={`/labs/${lab.slug}`} className="block">
      <GlassPanel radius="xl" interactive className="flex h-full flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-title text-[15px] font-semibold">{lab.title}</h3>
          {passed ? (
            <span className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--color-success)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]">
              <Check className="size-3" aria-hidden />
              Passed
            </span>
          ) : (
            lab.bestScore !== null && (
              <span className="shrink-0 rounded-full bg-[var(--surface-sunken)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                Best {Math.round(lab.bestScore)}%
              </span>
            )
          )}
        </div>

        {lab.description && (
          <p className="flex-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {lab.description}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px] text-[var(--text-tertiary)]">
          <span
            className="rounded-full px-2 py-0.5 font-medium capitalize"
            style={{
              backgroundColor: `color-mix(in oklab, ${color} 16%, transparent)`,
              color,
            }}
          >
            {lab.difficulty}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="size-3.5" aria-hidden />
            {lab.estimatedMinutes} min
          </span>
          <span>
            {lab.objectiveCount} objective{lab.objectiveCount === 1 ? '' : 's'}
          </span>
          <span className="ml-auto font-medium text-accent-500">+{lab.xpReward} XP</span>
        </div>
      </GlassPanel>
    </Link>
  );
}

export default function LabsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: labKeys.list,
    queryFn: labApi.list,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading labs" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Could not load the lab library">
          Please try again in a moment.
        </Alert>
      </div>
    );
  }

  const byKind = KIND_ORDER.map((kind) => ({
    kind,
    labs: data.items.filter((lab) => lab.kind === kind),
  })).filter((group) => group.labs.length > 0);

  const passedCount = data.items.filter((lab) => lab.status === 'passed').length;

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-title text-2xl font-semibold">Hands-on labs</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Build it, break it, fix it. Every lab is graded by running real traffic
          over the network you configure.
        </p>
        {data.items.length > 0 && (
          <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">
            {passedCount} of {data.items.length} passed
          </p>
        )}
      </header>

      {byKind.map((group, groupIndex) => {
        const Icon = KIND_ICONS[group.kind];
        return (
          <motion.section
            key={group.kind}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: groupIndex * 0.05 }}
            className="flex flex-col gap-4"
          >
            <div className="flex items-baseline gap-3">
              <h2 className="text-title flex items-center gap-2 text-lg font-semibold">
                <Icon className="size-4 text-accent-500" aria-hidden />
                {LAB_KIND_LABELS[group.kind]}
              </h2>
              <p className={cn('text-[13px] text-[var(--text-tertiary)]')}>
                {LAB_KIND_BLURBS[group.kind]}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.labs.map((lab) => (
                <LabCard key={lab.id} lab={lab} />
              ))}
            </div>
          </motion.section>
        );
      })}

      {data.items.length === 0 && (
        <Alert tone="info" title="No labs yet">
          Labs will appear here as they are published.
        </Alert>
      )}
    </div>
  );
}
