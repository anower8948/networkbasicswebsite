import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './api-client';

/**
 * Shared TanStack Query configuration.
 *
 * Retries are suppressed for 4xx responses: a 401, 403, 404 or 422 will never
 * succeed on a second attempt, and retrying them only delays the error the user
 * needs to see.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
    },
  },
});

/** Centralised cache keys — prevents typo-driven cache misses across features. */
export const queryKeys = {
  currentUser: ['auth', 'me'] as const,
  sessions: ['auth', 'sessions'] as const,
  progress: ['users', 'me', 'progress'] as const,
  users: (limit: number, offset: number) => ['users', { limit, offset }] as const,
} as const;

/** Topology editor cache keys. */
export const topologyKeys = {
  catalog: ['topology', 'device-catalog'] as const,
  list: ['topology', 'list'] as const,
  detail: (id: string) => ['topology', 'detail', id] as const,
} as const;

/** Recognition surface: badges, boards, certificates. */
export const gamificationKeys = {
  achievements: ['gamification', 'achievements'] as const,
  leaderboard: (scope: string) => ['gamification', 'leaderboard', scope] as const,
  certificates: ['gamification', 'certificates'] as const,
} as const;

/** Notes and bookmarks. */
export const notesKeys = {
  all: ['notes', 'all'] as const,
  forLesson: (lessonId: string) => ['notes', 'lesson', lessonId] as const,
  bookmarks: ['notes', 'bookmarks'] as const,
} as const;

/** Instructor and admin tooling. */
export const adminKeys = {
  analytics: ['admin', 'analytics'] as const,
  roster: ['admin', 'roster'] as const,
} as const;

/** Lab library and attempt cache keys. */
export const labKeys = {
  list: ['labs', 'list'] as const,
  detail: (slug: string) => ['labs', 'detail', slug] as const,
  attempt: (slug: string) => ['labs', 'attempt', slug] as const,
} as const;

/** Catalogue and lesson cache keys. */
export const learningKeys = {
  tracks: ['learning', 'tracks'] as const,
  enrollments: ['learning', 'enrollments'] as const,
  course: (slug: string) => ['learning', 'course', slug] as const,
  lesson: (courseSlug: string, lessonSlug: string) =>
    ['learning', 'lesson', courseSlug, lessonSlug] as const,
  quizAttempts: (quizId: string) => ['learning', 'quiz', quizId, 'attempts'] as const,
} as const;
