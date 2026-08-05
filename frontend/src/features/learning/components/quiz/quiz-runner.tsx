/**
 * Runs a quiz attempt: renders each question type, collects answers, submits,
 * and shows graded feedback.
 *
 * Correct answers only exist client-side *after* submission — the pre-submission
 * payload has none, so there is nothing to inspect in devtools during an attempt.
 */

import { useMutation } from '@tanstack/react-query';
import { useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, RotateCcw, XCircle } from 'lucide-react';
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { learningApi } from '@/features/learning/api/learning-api';
import { QuestionInput } from './question-input';
import { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/cn';
import { learningKeys, queryKeys } from '@/lib/query-client';
import type {
  QuestionResult,
  QuizAnswer,
  QuizForAttempt,
  QuizQuestionForAttempt,
  QuizResult,
} from '@/types/learning';

interface QuizRunnerProps {
  quiz: QuizForAttempt;
  courseSlug: string;
  lessonSlug: string;
  onRetry: () => void;
}

function ResultBanner({ result }: { result: QuizResult }) {
  const tone = result.passed ? 'success' : 'danger';
  const Icon = result.passed ? CheckCircle2 : XCircle;

  return (
    <Alert tone={tone}>
      <div className="flex items-start gap-3">
        <Icon
          className="mt-0.5 size-6 shrink-0"
          style={{ color: `var(--color-${result.passed ? 'success' : 'danger'})` }}
          aria-hidden
        />
        <div>
          <p className="text-[15px] font-semibold">
            {result.passed ? 'Passed' : 'Not passed'} — {result.scorePercent}%
          </p>
          <p className="mt-1 text-[13px]">
            {result.pointsEarned} of {result.pointsPossible} points. You need{' '}
            {result.passingScore}% to pass.
          </p>
          {result.xpAwarded > 0 && (
            <p className="mt-1 text-[13px] font-medium text-accent-600 dark:text-accent-400">
              +{result.xpAwarded} XP
              {result.leveledUp && ` · levelled up to ${result.level}!`}
            </p>
          )}
        </div>
      </div>
    </Alert>
  );
}

function QuestionFeedback({
  question,
  result,
}: {
  question: QuizQuestionForAttempt;
  result: QuestionResult;
}) {
  const correctLabels = question.options
    .filter((option) => result.correctOptionIds.includes(option.id))
    .map((option) => option.text);

  return (
    <div
      className={cn(
        'mt-3 rounded-[var(--radius-sm)] border p-3.5 text-[13px]',
        result.isCorrect
          ? 'border-[var(--color-success)]/30 bg-[var(--color-success)]/8'
          : 'border-[var(--color-danger)]/30 bg-[var(--color-danger)]/8',
      )}
    >
      <p
        className="font-semibold"
        style={{ color: `var(--color-${result.isCorrect ? 'success' : 'danger'})` }}
      >
        {result.isCorrect ? 'Correct' : 'Incorrect'} · {result.pointsEarned}/
        {result.pointsPossible} points
      </p>

      {!result.isCorrect && (
        <p className="mt-1.5 text-[var(--text-secondary)]">
          <span className="font-medium">Correct answer: </span>
          {correctLabels.length > 0
            ? correctLabels.join(', ')
            : result.correctOrder.length > 0
              ? result.correctOrder.join(' → ')
              : (result.correctText ?? '—')}
        </p>
      )}

      {result.explanation && (
        <p className="mt-1.5 leading-relaxed text-[var(--text-secondary)]">
          {result.explanation}
        </p>
      )}
    </div>
  );
}

export function QuizRunner({ quiz, courseSlug, lessonSlug, onRetry }: QuizRunnerProps) {
  const [answers, setAnswers] = useState<Record<string, QuizAnswer>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const queryClient = useQueryClient();

  const submit = useMutation({
    mutationFn: () =>
      learningApi.submitAttempt(
        quiz.attemptId,
        // Every question is submitted, answered or not, so the server grades a
        // complete set and reports omissions as wrong rather than missing.
        quiz.questions.map(
          (question) => answers[question.id] ?? { questionId: question.id },
        ),
      ),
    onSuccess: (graded) => {
      setResult(graded);
      // Passing pays XP and can complete the lesson, so refresh both views.
      void queryClient.invalidateQueries({ queryKey: queryKeys.progress });
      void queryClient.invalidateQueries({
        queryKey: learningKeys.lesson(courseSlug, lessonSlug),
      });
      void queryClient.invalidateQueries({ queryKey: learningKeys.course(courseSlug) });
    },
  });

  const answeredCount = quiz.questions.filter((question) => {
    const answer = answers[question.id];
    if (!answer) return false;
    return Boolean(
      answer.optionIds?.length ||
        answer.text?.trim() ||
        answer.values?.length ||
        Object.keys(answer.pairs ?? {}).length,
    );
  }).length;

  const resultsById = new Map(result?.results.map((item) => [item.questionId, item]) ?? []);

  return (
    <div className="flex flex-col gap-4">
      <GlassPanel radius="lg" className="p-5">
        <h3 className="text-title text-base font-semibold">{quiz.title}</h3>
        {quiz.instructions && (
          <p className="mt-1.5 text-[13px] text-[var(--text-secondary)]">{quiz.instructions}</p>
        )}
        <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">
          Attempt {quiz.attemptNumber}
          {quiz.attemptsRemaining !== null && ` · ${quiz.attemptsRemaining} remaining`}
        </p>
      </GlassPanel>

      {result && <ResultBanner result={result} />}

      {quiz.questions.map((question, index) => {
        const feedback = resultsById.get(question.id);

        return (
          <GlassPanel key={question.id} radius="lg" className="p-5">
            <div className="flex items-baseline gap-3">
              <span className="text-[12px] font-medium text-[var(--text-tertiary)]">
                {index + 1}
              </span>
              <p className="flex-1 text-[15px] leading-relaxed font-medium">{question.prompt}</p>
              <span className="shrink-0 text-[12px] text-[var(--text-tertiary)]">
                {question.points} pt{question.points === 1 ? '' : 's'}
              </span>
            </div>

            <div className="mt-4">
              <QuestionInput
                question={question}
                answer={answers[question.id]}
                disabled={result !== null}
                onChange={(update) =>
                  setAnswers((current) => ({
                    ...current,
                    // Updater form resolves against the live state, so two
                    // rapid multi-select clicks cannot drop each other.
                    [question.id]:
                      typeof update === 'function' ? update(current[question.id]) : update,
                  }))
                }
              />
            </div>

            {feedback && <QuestionFeedback question={question} result={feedback} />}
          </GlassPanel>
        );
      })}

      {submit.error instanceof ApiError && (
        <Alert tone="danger">{submit.error.message}</Alert>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-[var(--text-tertiary)]">
          {result
            ? `Scored ${result.scorePercent}%`
            : `${answeredCount} of ${quiz.questions.length} answered`}
        </p>

        {result ? (
          <Button
            variant="secondary"
            leadingIcon={<RotateCcw className="size-4" />}
            onClick={() => {
              setResult(null);
              setAnswers({});
              onRetry();
            }}
          >
            Try again
          </Button>
        ) : (
          <Button
            size="lg"
            isLoading={submit.isPending}
            onClick={() => submit.mutate()}
            disabled={answeredCount === 0}
          >
            Submit answers
          </Button>
        )}
      </div>
    </div>
  );
}
