/**
 * The lab checklist: objectives, their state, and why each one is not done yet.
 *
 * The design principle is that a failed check should read like a colleague
 * looking over your shoulder, not like a test runner. Each objective expands to
 * the individual checks behind it, and each check says what was asked and what
 * was actually found — the server's `summary` and `detail`.
 *
 * Hints are per-objective and requested explicitly. They are not rationed, but
 * they are counted, so an instructor can see which objective a cohort gets
 * stuck on.
 */

import {
  Check,
  ChevronDown,
  CircleDashed,
  Lightbulb,
  X,
} from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import type { CheckResult, LabObjective, ObjectiveResult } from '@/types/lab';

interface ObjectivesPanelProps {
  objectives: LabObjective[];
  /** Absent until the learner has checked their work at least once. */
  results: ObjectiveResult[];
  checks: CheckResult[];
  hints: Record<string, string | null>;
  isRequestingHint: boolean;
  onRequestHint: (objectiveId: string) => void;
}

function ObjectiveIcon({ state }: { state: 'passed' | 'failed' | 'unchecked' }) {
  if (state === 'passed') {
    return (
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--color-success)]">
        <Check className="size-2.5 text-white" aria-hidden />
      </span>
    );
  }
  if (state === 'failed') {
    return (
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-[var(--color-danger)]">
        <X className="size-2.5 text-white" aria-hidden />
      </span>
    );
  }
  return (
    <CircleDashed
      className="mt-0.5 size-4 shrink-0 text-[var(--text-tertiary)]"
      aria-hidden
    />
  );
}

export function ObjectivesPanel({
  objectives,
  results,
  checks,
  hints,
  isRequestingHint,
  onRequestHint,
}: ObjectivesPanelProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const resultFor = (id: string) => results.find((item) => item.objectiveId === id);

  return (
    <ol className="flex flex-col gap-1.5 p-3" aria-label="Lab objectives">
      {objectives.map((objective) => {
        const result = resultFor(objective.id);
        // No result at all means "not checked yet" — which is different from
        // failed, and must not be shown as a red cross before they have tried.
        const state = result === undefined ? 'unchecked' : result.passed ? 'passed' : 'failed';
        const related = checks.filter((item) => item.objectiveId === objective.id);
        const isOpen = expanded === objective.id;
        const hint = hints[objective.id];

        return (
          <li key={objective.id}>
            <div
              className={cn(
                'rounded-[var(--radius-sm)] border px-3 py-2 transition-colors',
                state === 'passed'
                  ? 'border-[var(--color-success)]/30 bg-[var(--color-success)]/8'
                  : state === 'failed'
                    ? 'border-[var(--color-danger)]/30 bg-[var(--color-danger)]/8'
                    : 'border-transparent bg-[var(--surface-sunken)]/50',
              )}
            >
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : objective.id)}
                className="flex w-full items-start gap-2 text-left"
                aria-expanded={isOpen}
              >
                <ObjectiveIcon state={state} />
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      'block text-[13px] leading-snug',
                      state === 'passed' && 'text-[var(--text-secondary)] line-through',
                    )}
                  >
                    {objective.title}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-[var(--text-tertiary)]">
                  {result ? `${result.pointsEarned}/${result.pointsPossible}` : objective.points}
                </span>
                <ChevronDown
                  className={cn(
                    'mt-0.5 size-3.5 shrink-0 text-[var(--text-tertiary)] transition-transform',
                    isOpen && 'rotate-180',
                  )}
                  aria-hidden
                />
              </button>

              {isOpen && (
                <div className="mt-2 flex flex-col gap-2 pl-6">
                  {related.length === 0 ? (
                    <p className="text-[12px] leading-relaxed text-[var(--text-tertiary)]">
                      Check your work to see how this one is doing.
                    </p>
                  ) : (
                    related.map((check) => (
                      <div key={check.ruleId} className="flex items-start gap-2">
                        <span
                          aria-hidden
                          className={cn(
                            'mt-1.5 size-1.5 shrink-0 rounded-full',
                            check.passed
                              ? 'bg-[var(--color-success)]'
                              : 'bg-[var(--color-danger)]',
                          )}
                        />
                        <span className="min-w-0">
                          <span className="block text-[12px] leading-snug text-[var(--text-secondary)]">
                            {check.summary}
                          </span>
                          {check.detail && (
                            <span
                              className={cn(
                                'mt-0.5 block text-[12px] leading-relaxed',
                                check.passed
                                  ? 'text-[var(--text-tertiary)]'
                                  : 'text-[var(--color-danger)]',
                              )}
                            >
                              {check.detail}
                            </span>
                          )}
                        </span>
                      </div>
                    ))
                  )}

                  {hint ? (
                    <p className="flex items-start gap-2 rounded-[var(--radius-xs)] bg-[var(--color-warning)]/10 px-2 py-1.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">
                      <Lightbulb
                        className="mt-0.5 size-3.5 shrink-0 text-[var(--color-warning)]"
                        aria-hidden
                      />
                      {hint}
                    </p>
                  ) : (
                    objective.hint !== null && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="self-start"
                        isLoading={isRequestingHint}
                        leadingIcon={<Lightbulb className="size-3.5" />}
                        onClick={() => onRequestHint(objective.id)}
                      >
                        Show a hint
                      </Button>
                    )
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
