/**
 * The lesson viewer.
 *
 * Renders the content blocks, autosaves reading position and study time, runs
 * the attached quiz, and marks the lesson complete.
 */

import { useMutation } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Check, ChevronLeft, ChevronRight, Clock, Target, Trophy, Zap } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { learningApi } from '@/features/learning/api/learning-api';
import { BlockRenderer } from '@/features/learning/components/blocks/block-renderer';
import { QuizRunner } from '@/features/learning/components/quiz/quiz-runner';
import { useCompleteLesson, useLesson } from '@/features/learning/hooks/use-catalog';
import { useStudyTimer } from '@/features/learning/hooks/use-study-timer';
import { LessonNotes } from '@/features/notes/components/lesson-notes';
import type { LessonCompletionResult, QuizForAttempt } from '@/types/learning';

export default function LessonPage() {
  const { courseSlug = '', lessonSlug = '' } = useParams();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  const { data: lesson, isLoading, error } = useLesson(courseSlug, lessonSlug);
  const complete = useCompleteLesson(courseSlug, lessonSlug);

  const [completion, setCompletion] = useState<LessonCompletionResult | null>(null);
  const [quiz, setQuiz] = useState<QuizForAttempt | null>(null);

  const startQuiz = useMutation({
    mutationFn: (quizId: string) => learningApi.startAttempt(quizId),
    onSuccess: setQuiz,
  });

  // Autosaves study time while the lesson is open.
  useStudyTimer({
    lessonId: lesson?.id ?? null,
    enabled: isAuthenticated && Boolean(lesson),
  });

  // Reset per-lesson UI when navigating between lessons — the component is
  // reused across routes, so stale completion state would leak across.
  const lastLessonId = useRef<string | null>(null);
  useEffect(() => {
    if (lesson && lesson.id !== lastLessonId.current) {
      lastLessonId.current = lesson.id;
      setCompletion(null);
      setQuiz(null);
      window.scrollTo({ top: 0 });
    }
  }, [lesson]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading lesson" />
      </div>
    );
  }

  if (error || !lesson) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Lesson not found">
          That lesson does not exist.{' '}
          <Link to="/courses" className="font-medium underline">
            Back to courses
          </Link>
        </Alert>
      </div>
    );
  }

  const isComplete = completion !== null || lesson.status === 'completed';

  const handleComplete = async () => {
    const result = await complete.mutateAsync(lesson.id);
    setCompletion(result);
  };

  const goToNext = () => {
    if (lesson.nextLesson) {
      void navigate(`/courses/${courseSlug}/${lesson.nextLesson.slug}`);
    } else {
      void navigate(`/courses/${courseSlug}`);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <nav className="flex items-center gap-1.5 text-[13px] text-[var(--text-secondary)]">
        <Link to="/courses" className="transition-colors hover:text-[var(--text-primary)]">
          Courses
        </Link>
        <span className="text-[var(--text-tertiary)]">/</span>
        <Link
          to={`/courses/${courseSlug}`}
          className="transition-colors hover:text-[var(--text-primary)]"
        >
          {lesson.courseTitle}
        </Link>
      </nav>

      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <p className="text-[12px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
          {lesson.moduleTitle}
        </p>
        <h1 className="text-display mt-1.5 text-[28px] leading-tight font-semibold">
          {lesson.title}
        </h1>
        {lesson.summary && (
          <p className="mt-2 text-[15px] leading-relaxed text-[var(--text-secondary)]">
            {lesson.summary}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[13px] text-[var(--text-tertiary)]">
          <span className="flex items-center gap-1.5">
            <Clock className="size-3.5" aria-hidden />
            {lesson.estimatedMinutes} min
          </span>
          <span className="flex items-center gap-1.5">
            <Zap className="size-3.5" aria-hidden />
            {lesson.xpReward} XP
          </span>
          {isComplete && (
            <span className="flex items-center gap-1.5 text-[var(--color-success)]">
              <Check className="size-3.5" aria-hidden />
              Completed
            </span>
          )}
        </div>
      </motion.header>

      {lesson.objectives.length > 0 && (
        <GlassPanel material="thin" radius="lg" className="p-5">
          <p className="flex items-center gap-2 text-[13px] font-semibold">
            <Target className="size-4 text-accent-500" aria-hidden />
            What you will learn
          </p>
          <ul className="mt-2.5 flex flex-col gap-1.5 pl-5 text-[14px] text-[var(--text-secondary)] list-disc marker:text-[var(--text-tertiary)]">
            {lesson.objectives.map((objective) => (
              <li key={objective}>{objective}</li>
            ))}
          </ul>
        </GlassPanel>
      )}

      <article>
        {lesson.contentBlocks.map((block, index) => (
          <BlockRenderer key={index} block={block} />
        ))}
      </article>

      {lesson.hasQuiz && lesson.quizId && (
        <section aria-label="Knowledge check" className="hairline-t flex flex-col gap-4 pt-8">
          <h2 className="text-title text-lg font-semibold">Knowledge check</h2>

          {!isAuthenticated ? (
            <Alert tone="info">
              <Link to="/login" className="font-medium underline">
                Sign in
              </Link>{' '}
              to take the quiz and earn XP.
            </Alert>
          ) : quiz ? (
            <QuizRunner
              quiz={quiz}
              courseSlug={courseSlug}
              lessonSlug={lessonSlug}
              onRetry={() => {
                setQuiz(null);
                startQuiz.mutate(lesson.quizId as string);
              }}
            />
          ) : (
            <GlassPanel radius="lg" className="flex flex-wrap items-center justify-between gap-3 p-5">
              <p className="text-[14px] text-[var(--text-secondary)]">
                Test what you have just read.
              </p>
              <Button
                isLoading={startQuiz.isPending}
                onClick={() => startQuiz.mutate(lesson.quizId as string)}
              >
                Start quiz
              </Button>
            </GlassPanel>
          )}
        </section>
      )}

      {isAuthenticated && <LessonNotes lessonId={lesson.id} />}

      {completion && (
        <Alert tone="success" title={completion.courseCompleted ? 'Course complete!' : 'Lesson complete'}>
          {completion.xpAwarded > 0 ? (
            <>
              +{completion.xpAwarded} XP
              {completion.leveledUp && ` · levelled up to ${completion.level}!`}
            </>
          ) : (
            'You had already completed this lesson.'
          )}
          {completion.newAchievements.length > 0 && (
            <span className="mt-2 block">
              <span className="flex items-center gap-1.5 font-medium">
                <Trophy className="size-3.5" aria-hidden />
                {completion.newAchievements.length === 1
                  ? 'Achievement unlocked'
                  : `${completion.newAchievements.length} achievements unlocked`}
              </span>
              <span className="mt-0.5 block">
                {completion.newAchievements.map((item) => item.title).join(', ')}
              </span>
            </span>
          )}
        </Alert>
      )}

      {isAuthenticated && !isComplete && (
        <GlassPanel radius="lg" className="flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="text-[14px] text-[var(--text-secondary)]">
            Finished reading? Mark it complete to earn {lesson.xpReward} XP.
          </p>
          <Button isLoading={complete.isPending} onClick={() => void handleComplete()}>
            Mark as complete
          </Button>
        </GlassPanel>
      )}

      {complete.error && (
        <Alert tone="warning">
          Enrol in this course from the{' '}
          <Link to={`/courses/${courseSlug}`} className="font-medium underline">
            course page
          </Link>{' '}
          before tracking progress.
        </Alert>
      )}

      <nav className="hairline-t flex items-center justify-between gap-3 pt-6">
        {lesson.previousLesson ? (
          <Link
            to={`/courses/${courseSlug}/${lesson.previousLesson.slug}`}
            className="group flex min-w-0 items-center gap-2 text-[13px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
          >
            <ChevronLeft className="size-4 shrink-0" aria-hidden />
            <span className="min-w-0">
              <span className="block text-[11px] text-[var(--text-tertiary)]">Previous</span>
              <span className="block truncate">{lesson.previousLesson.title}</span>
            </span>
          </Link>
        ) : (
          <span />
        )}

        {lesson.nextLesson ? (
          <Button variant="secondary" onClick={goToNext} trailingIcon={<ChevronRight className="size-4" />}>
            Next lesson
          </Button>
        ) : (
          <Button variant="secondary" onClick={goToNext}>
            Back to course
          </Button>
        )}
      </nav>
    </div>
  );
}
