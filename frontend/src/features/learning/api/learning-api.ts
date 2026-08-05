/** Catalogue, lesson, and quiz endpoints. */

import { apiClient } from '@/lib/api-client';
import type {
  CourseDetail,
  Enrollment,
  EnrollmentWithCourse,
  LessonCompletionResult,
  LessonDetail,
  LessonProgress,
  QuizAnswer,
  QuizAttemptSummary,
  QuizForAttempt,
  QuizResult,
  TrackWithCourses,
} from '@/types/learning';

export const learningApi = {
  /* ---- Catalogue (public) -------------------------------------------- */

  tracks: () => apiClient.get<TrackWithCourses[]>('/courses/tracks'),

  course: (slug: string) => apiClient.get<CourseDetail>(`/courses/${slug}`),

  lesson: (courseSlug: string, lessonSlug: string) =>
    apiClient.get<LessonDetail>(`/lessons/${courseSlug}/${lessonSlug}`),

  /* ---- Enrolment ------------------------------------------------------ */

  enrollments: () => apiClient.get<EnrollmentWithCourse[]>('/courses/enrollments'),

  enroll: (slug: string) => apiClient.post<Enrollment>(`/courses/${slug}/enroll`),

  /* ---- Progress ------------------------------------------------------- */

  savePosition: (lessonId: string, lastBlockIndex: number, timeSpentSeconds: number) =>
    apiClient.put<LessonProgress>(`/lessons/${lessonId}/progress`, {
      lastBlockIndex,
      timeSpentSeconds,
    }),

  completeLesson: (lessonId: string) =>
    apiClient.post<LessonCompletionResult>(`/lessons/${lessonId}/complete`),

  /* ---- Quizzes -------------------------------------------------------- */

  startAttempt: (quizId: string) =>
    apiClient.post<QuizForAttempt>(`/quizzes/${quizId}/attempts`),

  submitAttempt: (attemptId: string, answers: QuizAnswer[]) =>
    apiClient.post<QuizResult>(`/quizzes/attempts/${attemptId}/submit`, { answers }),

  attemptHistory: (quizId: string) =>
    apiClient.get<QuizAttemptSummary[]>(`/quizzes/${quizId}/attempts`),
};
