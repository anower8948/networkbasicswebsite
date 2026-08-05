/**
 * The lab workspace.
 *
 * The same editing surface as the simulator, wrapped in the machinery of an
 * assessment: a briefing, an objectives checklist, autosave, and two distinct
 * actions — **Check my work** (free, formative, unlimited) and **Submit**
 * (final, closes the attempt, pays XP).
 *
 * That split is deliberate. A learner who can only find out how they did by
 * ending the exercise will guess; one who can check as often as they like will
 * read the feedback and iterate, which is the whole point of a lab whose
 * grading is done by simulating real traffic.
 *
 * Work is autosaved. Unlike the free-form designer — where saving over an
 * experiment you meant to abandon would be destructive — an attempt *is* the
 * learner's work in progress, and losing it to a closed tab would be the worse
 * outcome.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Info,
  Send,
  Trophy,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import '@xyflow/react/dist/style.css';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { ObjectivesPanel } from '@/features/labs/components/objectives-panel';
import { labApi } from '@/features/labs/api/lab-api';
import { topologyApi } from '@/features/topology/api/topology-api';
import { TopologyWorkspace } from '@/features/topology/components/topology-workspace';
import { useTopologyEditor } from '@/features/topology/hooks/use-topology-editor';
import { labKeys, topologyKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';
import {
  LAB_KIND_LABELS,
  type LabAttempt,
  type LabDetail,
  type LabGradeResult,
} from '@/types/lab';
import type { LinkIssue } from '@/types/topology';

const AUTOSAVE_MS = 4000;

function Briefing({ lab, hintsUsed }: { lab: LabDetail; hintsUsed: number }) {
  return (
    <div className="flex flex-col gap-4 p-3">
      <div>
        <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[11px] font-medium text-accent-500">
          {LAB_KIND_LABELS[lab.kind]}
        </span>
        <h3 className="text-title mt-2 text-[14px] font-semibold">{lab.title}</h3>
        {lab.description && (
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--text-secondary)]">
            {lab.description}
          </p>
        )}
      </div>

      <div>
        <h4 className="text-[12px] font-semibold text-[var(--text-secondary)]">
          Requirements
        </h4>
        <ul className="mt-1.5 flex flex-col gap-1.5">
          {lab.requirements.map((requirement) => (
            <li
              key={requirement}
              className="flex items-start gap-2 text-[12px] leading-relaxed text-[var(--text-secondary)]"
            >
              <Info
                className="mt-0.5 size-3 shrink-0 text-[var(--text-tertiary)]"
                aria-hidden
              />
              {requirement}
            </li>
          ))}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-2 text-[12px]">
        <div>
          <dt className="text-[var(--text-tertiary)]">Pass mark</dt>
          <dd className="font-medium">{lab.passingScore}%</dd>
        </div>
        <div>
          <dt className="text-[var(--text-tertiary)]">Reward</dt>
          <dd className="font-medium text-accent-500">+{lab.xpReward} XP</dd>
        </div>
        <div>
          <dt className="text-[var(--text-tertiary)]">Estimated</dt>
          <dd className="font-medium">{lab.estimatedMinutes} min</dd>
        </div>
        <div>
          <dt className="text-[var(--text-tertiary)]">Hints used</dt>
          <dd className="font-medium">{hintsUsed}</dd>
        </div>
      </dl>
    </div>
  );
}

function LabInner({ lab, attempt }: { lab: LabDetail; attempt: LabAttempt }) {
  const { data: catalog = [] } = useQuery({
    queryKey: topologyKeys.catalog,
    queryFn: topologyApi.deviceCatalog,
    staleTime: Infinity,
  });

  const editor = useTopologyEditor(attempt.workingTopology, catalog);
  const [issues, setIssues] = useState<LinkIssue[]>([]);
  const [grade, setGrade] = useState<LabGradeResult | null>(null);
  const [hints, setHints] = useState<Record<string, string | null>>({});
  const [hintsUsed, setHintsUsed] = useState(attempt.hintsUsed);
  const startedAt = useRef(Date.now());

  const save = useMutation({
    mutationFn: () =>
      labApi.saveTopology(
        attempt.id,
        editor.document,
        Math.round((Date.now() - startedAt.current) / 1000) + attempt.timeSpentSeconds,
      ),
    onSuccess: () => editor.markSaved(),
  });

  const check = useMutation({
    mutationFn: () => labApi.check(attempt.id),
    onSuccess: setGrade,
  });

  const submit = useMutation({
    mutationFn: () => labApi.submit(attempt.id),
    onSuccess: setGrade,
  });

  const hint = useMutation({
    mutationFn: (objectiveId: string) => labApi.hint(attempt.id, objectiveId),
    onSuccess: (response) => {
      setHints((current) => ({ ...current, [response.objectiveId]: response.hint }));
      setHintsUsed(response.hintsUsed);
    },
  });

  const connect = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      topologyApi.suggestLink(editor.document, source, target),
    onSuccess: (suggestion, { source, target }) => {
      const link = editor.addLink({
        source: { deviceId: source, interface: suggestion.sourceInterface },
        target: { deviceId: target, interface: suggestion.targetInterface },
        cable: suggestion.cable,
        enabled: true,
        label: null,
      });
      if (suggestion.warning) {
        setIssues((current) => [
          ...current,
          { linkId: link.id, message: suggestion.warning as string },
        ]);
      }
    },
  });

  const handleConnect = useCallback(
    (source: string, target: string) => connect.mutate({ source, target }),
    [connect],
  );

  // Autosave the working topology. Debounced rather than fired per edit: a
  // drag produces a change per animation frame.
  const isDirty = editor.isDirty;
  const savePending = save.isPending;
  useEffect(() => {
    if (!isDirty || savePending) return;
    const timer = setTimeout(() => save.mutate(), AUTOSAVE_MS);
    return () => clearTimeout(timer);
    // `save` is a stable mutation object; including it would restart the timer
    // on every render and the autosave would never fire.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDirty, savePending]);

  /** Grading runs server-side against the *saved* document, so save first. */
  const gradeNow = async (final: boolean) => {
    await save.mutateAsync();
    if (final) submit.mutate();
    else check.mutate();
  };

  const isSubmitted = grade?.status === 'passed' || grade?.status === 'failed';
  const score = grade?.scorePercent ?? attempt.scorePercent;

  return (
    <div className="flex h-[calc(100dvh-8rem)] min-h-[540px] flex-col gap-3">
      <header className="flex flex-wrap items-center gap-3">
        <Link
          to="/labs"
          className="flex items-center gap-1.5 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Labs
        </Link>

        <h1 className="text-title text-[15px] font-semibold">{lab.title}</h1>

        <span className="text-[12px] text-[var(--text-tertiary)]">
          {editor.isDirty || save.isPending ? 'Saving…' : 'Saved'}
        </span>

        {score !== null && (
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[12px] font-medium',
              score >= lab.passingScore
                ? 'bg-[var(--color-success)]/15 text-[var(--color-success)]'
                : 'bg-[var(--surface-sunken)] text-[var(--text-secondary)]',
            )}
          >
            {Math.round(score)}%
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={<ClipboardCheck className="size-4" />}
            isLoading={check.isPending}
            disabled={isSubmitted}
            onClick={() => void gradeNow(false)}
          >
            Check my work
          </Button>
          <Button
            size="sm"
            leadingIcon={<Send className="size-4" />}
            isLoading={submit.isPending}
            disabled={isSubmitted}
            onClick={() => void gradeNow(true)}
          >
            Submit
          </Button>
        </div>
      </header>

      {grade && isSubmitted && (
        <Alert tone={grade.passed ? 'success' : 'danger'}>
          <span className="flex items-start gap-2">
            {grade.passed ? (
              <Trophy className="mt-0.5 size-4 shrink-0" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
            )}
            <span>
              <span className="block font-medium">
                {grade.passed
                  ? `Passed with ${Math.round(grade.scorePercent)}%`
                  : `Scored ${Math.round(grade.scorePercent)}% — ${lab.passingScore}% is needed to pass`}
              </span>
              {grade.xpAwarded > 0 && (
                <span className="mt-0.5 block">+{grade.xpAwarded} XP earned.</span>
              )}
              {!grade.passed && (
                <span className="mt-0.5 block">
                  Open the lab again from the library to start a fresh attempt.
                </span>
              )}
              {grade.faultExplanations.length > 0 && (
                <span className="mt-2 block">
                  <span className="block font-medium">What had been broken:</span>
                  <ul className="mt-1 flex list-disc flex-col gap-1 pl-4">
                    {grade.faultExplanations.map((explanation) => (
                      <li key={explanation}>{explanation}</li>
                    ))}
                  </ul>
                </span>
              )}
            </span>
          </span>
        </Alert>
      )}

      <TopologyWorkspace
        editor={editor}
        catalog={catalog}
        issues={issues}
        onConnect={handleConnect}
        leadingTabs={[
          {
            id: 'brief',
            label: 'Brief',
            content: <Briefing lab={lab} hintsUsed={hintsUsed} />,
          },
          {
            id: 'objectives',
            label: 'Tasks',
            content: (
              <ObjectivesPanel
                objectives={lab.objectives}
                results={grade?.objectives ?? []}
                checks={grade?.results ?? attempt.checkResults}
                hints={hints}
                isRequestingHint={hint.isPending}
                onRequestHint={(objectiveId) => hint.mutate(objectiveId)}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

export default function LabPage() {
  const { slug } = useParams();

  const labQuery = useQuery({
    queryKey: labKeys.detail(slug ?? ''),
    queryFn: () => labApi.get(slug as string),
    enabled: Boolean(slug),
  });

  // Starting an attempt is a POST, but it is idempotent — it resumes an open
  // attempt rather than creating a second — so it is safe to run as a query on
  // mount, and that is what lets a refresh land back in the same workspace.
  const attemptQuery = useQuery({
    queryKey: labKeys.attempt(slug ?? ''),
    queryFn: () => labApi.startAttempt(slug as string),
    enabled: Boolean(slug) && labQuery.isSuccess,
    staleTime: Infinity,
    refetchOnMount: false,
  });

  if (labQuery.isLoading || attemptQuery.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Opening the lab" />
      </div>
    );
  }

  if (labQuery.error || !labQuery.data) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Lab not found">
          It may have been unpublished. <Link to="/labs">Back to the library</Link>.
        </Alert>
      </div>
    );
  }

  if (attemptQuery.error || !attemptQuery.data) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Could not start this lab">
          Please try again in a moment.
        </Alert>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <LabInner
        key={attemptQuery.data.id}
        lab={labQuery.data}
        attempt={attemptQuery.data}
      />
    </ReactFlowProvider>
  );
}
