import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { learningApi } from '@/features/learning/api/learning-api';
import { learningKeys, queryKeys } from '@/lib/query-client';

export function useTracks() {
  return useQuery({
    queryKey: learningKeys.tracks,
    queryFn: learningApi.tracks,
  });
}

export function useCourse(slug: string) {
  return useQuery({
    queryKey: learningKeys.course(slug),
    queryFn: () => learningApi.course(slug),
    enabled: Boolean(slug),
  });
}

export function useEnrollments() {
  return useQuery({
    queryKey: learningKeys.enrollments,
    queryFn: learningApi.enrollments,
  });
}

export function useEnroll(slug: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => learningApi.enroll(slug),
    onSuccess: () => {
      // The course page, the catalogue and "my courses" all show enrolment
      // state, so all three must be refetched.
      void queryClient.invalidateQueries({ queryKey: learningKeys.course(slug) });
      void queryClient.invalidateQueries({ queryKey: learningKeys.tracks });
      void queryClient.invalidateQueries({ queryKey: learningKeys.enrollments });
    },
  });
}

export function useLesson(courseSlug: string, lessonSlug: string) {
  return useQuery({
    queryKey: learningKeys.lesson(courseSlug, lessonSlug),
    queryFn: () => learningApi.lesson(courseSlug, lessonSlug),
    enabled: Boolean(courseSlug && lessonSlug),
  });
}

export function useCompleteLesson(courseSlug: string, lessonSlug: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (lessonId: string) => learningApi.completeLesson(lessonId),
    onSuccess: () => {
      // Completion moves XP, course percentage, and lesson status at once.
      void queryClient.invalidateQueries({ queryKey: learningKeys.lesson(courseSlug, lessonSlug) });
      void queryClient.invalidateQueries({ queryKey: learningKeys.course(courseSlug) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.progress });
      void queryClient.invalidateQueries({ queryKey: learningKeys.enrollments });
    },
  });
}
