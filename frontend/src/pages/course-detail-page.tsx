import { motion } from 'motion/react';
import {
  Award,
  BookOpen,
  Check,
  ChevronLeft,
  Circle,
  CircleDot,
  Clock,
  FileQuestion,
} from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { useCourse, useEnroll } from '@/features/learning/hooks/use-catalog';
import { cn } from '@/lib/cn';
import type { LessonSummary } from '@/types/learning';

function StatusIcon({ status }: { status: LessonSummary['status'] }) {
  if (status === 'completed') {
    return <Check className="size-4 text-[var(--color-success)]" aria-label="Completed" />;
  }
  if (status === 'in_progress') {
    return <CircleDot className="size-4 text-accent-500" aria-label="In progress" />;
  }
  return <Circle className="size-4 text-[var(--text-tertiary)]" aria-label="Not started" />;
}

export default function CourseDetailPage() {
  const { courseSlug = '' } = useParams();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { data: course, isLoading, error } = useCourse(courseSlug);
  const enroll = useEnroll(courseSlug);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading course" />
      </div>
    );
  }

  if (error || !course) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Course not found">
          That course does not exist, or is not published yet.{' '}
          <Link to="/courses" className="font-medium underline">
            Back to courses
          </Link>
        </Alert>
      </div>
    );
  }

  const nextLessonSlug = course.modules
    .flatMap((module) => module.lessons)
    .find((lesson) => lesson.id === course.nextLessonId)?.slug;

  const handleStart = () => {
    const target = nextLessonSlug ?? course.modules[0]?.lessons[0]?.slug;
    if (target) void navigate(`/courses/${course.slug}/${target}`);
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <Link
        to="/courses"
        className="inline-flex w-fit items-center gap-1.5 text-[13px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
      >
        <ChevronLeft className="size-4" aria-hidden />
        All courses
      </Link>

      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <h1 className="text-display text-[28px] leading-tight font-semibold">{course.title}</h1>
        {course.description && (
          <p className="mt-2.5 max-w-2xl text-[15px] leading-relaxed text-[var(--text-secondary)]">
            {course.description}
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-[var(--text-tertiary)]">
          <span className="flex items-center gap-1.5">
            <BookOpen className="size-4" aria-hidden />
            {course.lessonCount} lessons
          </span>
          <span className="flex items-center gap-1.5">
            <Clock className="size-4" aria-hidden />
            {course.estimatedMinutes} minutes
          </span>
          <span className="capitalize">{course.difficulty}</span>
          {course.grantsCertificate && (
            <span className="flex items-center gap-1.5">
              <Award className="size-4" aria-hidden />
              Certificate on completion
            </span>
          )}
        </div>
      </motion.header>

      <GlassPanel radius="xl" className="flex flex-col gap-4 p-5">
        {course.isEnrolled ? (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[13px] font-medium">Your progress</span>
              <span className="text-[13px] text-[var(--text-tertiary)] tabular-nums">
                {course.completedLessonCount} of {course.lessonCount} · {course.progressPercent}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-sunken)]">
              <motion.div
                className="h-full rounded-full bg-linear-to-r from-accent-400 to-accent-600"
                initial={{ width: 0 }}
                animate={{ width: `${course.progressPercent}%` }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <Button size="lg" onClick={handleStart} className="w-fit">
              {course.progressPercent > 0 ? 'Continue' : 'Start first lesson'}
            </Button>
          </>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-[var(--text-secondary)]">
              {isAuthenticated
                ? 'Enrol to track your progress and earn XP.'
                : 'Sign in to enrol and track your progress.'}
            </p>
            {isAuthenticated ? (
              <Button
                size="lg"
                isLoading={enroll.isPending}
                onClick={() => enroll.mutate()}
              >
                Enrol in this course
              </Button>
            ) : (
              <Link
                to="/login"
                className="inline-flex h-12 items-center rounded-[var(--radius-md)] bg-accent-500 px-6 text-base font-medium text-white transition-colors hover:bg-accent-600"
              >
                Sign in to enrol
              </Link>
            )}
          </div>
        )}
      </GlassPanel>

      <section aria-label="Syllabus" className="flex flex-col gap-4">
        <h2 className="text-title text-lg font-semibold">Syllabus</h2>

        {course.modules.map((module) => (
          <GlassPanel key={module.id} radius="xl" className="overflow-hidden">
            <div className="hairline-b px-5 py-3.5">
              <h3 className="text-[14px] font-semibold">{module.title}</h3>
              {module.description && (
                <p className="mt-0.5 text-[13px] text-[var(--text-secondary)]">
                  {module.description}
                </p>
              )}
            </div>

            <ul>
              {module.lessons.map((lesson) => (
                <li key={lesson.id} className="border-t border-[var(--hairline)] first:border-t-0">
                  <Link
                    to={`/courses/${course.slug}/${lesson.slug}`}
                    className={cn(
                      'flex items-center gap-3.5 px-5 py-3.5',
                      'transition-colors hover:bg-[var(--surface-sunken)]',
                    )}
                  >
                    <StatusIcon status={lesson.status} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14px] font-medium">{lesson.title}</span>
                      {lesson.summary && (
                        <span className="mt-0.5 block text-[13px] text-[var(--text-secondary)]">
                          {lesson.summary}
                        </span>
                      )}
                    </span>
                    <span className="flex shrink-0 items-center gap-3 text-[12px] text-[var(--text-tertiary)]">
                      {lesson.hasQuiz && (
                        <FileQuestion className="size-3.5" aria-label="Includes a quiz" />
                      )}
                      <span>{lesson.estimatedMinutes} min</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </GlassPanel>
        ))}
      </section>
    </div>
  );
}
