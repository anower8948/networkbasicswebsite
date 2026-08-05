/** Catalogue, progress, and quiz types. Mirrors the backend schemas. */

import type { ContentBlock } from './content';
import type { Achievement } from './gamification';

export type TrackLevel = 'foundation' | 'intermediate' | 'advanced';
export type Difficulty = 'beginner' | 'intermediate' | 'advanced' | 'expert';
export type LessonType = 'theory' | 'interactive' | 'simulation' | 'lab' | 'quiz' | 'assessment';
export type ProgressStatus = 'not_started' | 'in_progress' | 'completed';
export type EnrollmentStatus = 'active' | 'completed' | 'paused' | 'dropped';
export type AttemptStatus = 'in_progress' | 'submitted' | 'passed' | 'failed' | 'abandoned';

export type QuestionType =
  | 'single_choice'
  | 'multiple_choice'
  | 'true_false'
  | 'fill_blank'
  | 'ordering'
  | 'matching'
  | 'subnet_calc'
  | 'cli_command';

/* -------------------------------------------------------------------------- */
/* Catalogue                                                                   */
/* -------------------------------------------------------------------------- */

export interface CourseSummary {
  id: string;
  trackId: string;
  slug: string;
  title: string;
  summary: string | null;
  difficulty: Difficulty;
  estimatedMinutes: number;
  coverImageUrl: string | null;
  tags: string[];
  orderIndex: number;
  lessonCount: number;
  grantsCertificate: boolean;
  /** Present only when the learner is enrolled. */
  progressPercent: number | null;
  isEnrolled: boolean;
}

export interface TrackWithCourses {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  level: TrackLevel;
  icon: string | null;
  accentColor: string | null;
  orderIndex: number;
  courseCount: number;
  courses: CourseSummary[];
}

export interface LessonSummary {
  id: string;
  slug: string;
  title: string;
  summary: string | null;
  lessonType: LessonType;
  estimatedMinutes: number;
  xpReward: number;
  orderIndex: number;
  hasQuiz: boolean;
  /** `null` for anonymous visitors. */
  status: ProgressStatus | null;
}

export interface ModuleSummary {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  orderIndex: number;
  lessons: LessonSummary[];
}

export interface CourseDetail {
  id: string;
  trackId: string;
  slug: string;
  title: string;
  summary: string | null;
  description: string | null;
  difficulty: Difficulty;
  estimatedMinutes: number;
  coverImageUrl: string | null;
  tags: string[];
  prerequisites: string[];
  grantsCertificate: boolean;
  modules: ModuleSummary[];
  lessonCount: number;
  isEnrolled: boolean;
  progressPercent: number;
  completedLessonCount: number;
  nextLessonId: string | null;
}

export interface LessonNeighbour {
  id: string;
  slug: string;
  title: string;
}

export interface LessonDetail {
  id: string;
  moduleId: string;
  courseId: string;
  courseSlug: string;
  courseTitle: string;
  moduleTitle: string;
  slug: string;
  title: string;
  summary: string | null;
  lessonType: LessonType;
  objectives: string[];
  contentBlocks: ContentBlock[];
  estimatedMinutes: number;
  xpReward: number;
  orderIndex: number;
  hasQuiz: boolean;
  quizId: string | null;
  status: ProgressStatus;
  lastBlockIndex: number;
  previousLesson: LessonNeighbour | null;
  nextLesson: LessonNeighbour | null;
}

/* -------------------------------------------------------------------------- */
/* Enrolment and progress                                                      */
/* -------------------------------------------------------------------------- */

export interface Enrollment {
  id: string;
  courseId: string;
  status: EnrollmentStatus;
  progressPercent: number;
  lastLessonId: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface EnrollmentWithCourse extends Enrollment {
  course: CourseSummary;
}

export interface LessonProgress {
  lessonId: string;
  status: ProgressStatus;
  lastBlockIndex: number;
  timeSpentSeconds: number;
  completedAt: string | null;
}

export interface LessonCompletionResult {
  lessonId: string;
  status: ProgressStatus;
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
  courseProgressPercent: number;
  courseCompleted: boolean;
  nextLessonId: string | null;
  /** Badges this completion unlocked, so the UI can celebrate them at once. */
  newAchievements: Achievement[];
}

/* -------------------------------------------------------------------------- */
/* Quizzes                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * A quiz as delivered *before* submission.
 *
 * Note what is absent: no `isCorrect` on options, no explanations, no answer
 * key. The server sends a different type after grading.
 */
export interface QuizOptionForAttempt {
  id: string;
  text: string;
  orderIndex: number;
}

export interface QuizQuestionForAttempt {
  id: string;
  prompt: string;
  questionType: QuestionType;
  mediaUrl: string | null;
  points: number;
  orderIndex: number;
  options: QuizOptionForAttempt[];
  matchTargets: string[];
}

export interface QuizForAttempt {
  id: string;
  lessonId: string;
  title: string;
  instructions: string | null;
  passingScore: number;
  timeLimitSeconds: number | null;
  questions: QuizQuestionForAttempt[];
  attemptId: string;
  attemptNumber: number;
  attemptsRemaining: number | null;
}

/** One learner response. Which fields matter depends on the question type. */
export interface QuizAnswer {
  questionId: string;
  optionIds?: string[];
  text?: string;
  values?: string[];
  pairs?: Record<string, string>;
}

export interface QuestionResult {
  questionId: string;
  isCorrect: boolean;
  pointsEarned: number;
  pointsPossible: number;
  explanation: string | null;
  correctOptionIds: string[];
  correctText: string | null;
  correctOrder: string[];
  correctPairs: Record<string, string>;
}

export interface QuizResult {
  attemptId: string;
  quizId: string;
  lessonId: string;
  status: AttemptStatus;
  passed: boolean;
  scorePercent: number;
  pointsEarned: number;
  pointsPossible: number;
  passingScore: number;
  attemptNumber: number;
  attemptsRemaining: number | null;
  results: QuestionResult[];
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
  newAchievements: Achievement[];
}

export interface QuizAttemptSummary {
  id: string;
  attemptNumber: number;
  status: AttemptStatus;
  scorePercent: number | null;
  pointsEarned: number;
  pointsPossible: number;
  submittedAt: string | null;
}
