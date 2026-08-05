/** Instructor and admin endpoints. */

import { apiClient } from '@/lib/api-client';

export interface PlatformOverview {
  totalUsers: number;
  activeUsersWeek: number;
  newUsersWeek: number;
  totalEnrollments: number;
  lessonsCompleted: number;
  labsCompleted: number;
  quizzesTaken: number;
  certificatesIssued: number;
}

export interface CoursePerformance {
  courseId: string;
  slug: string;
  title: string;
  enrollments: number;
  completions: number;
  completionRate: number;
  averageProgress: number;
}

export interface LabPerformance {
  labId: string;
  slug: string;
  title: string;
  attempts: number;
  passes: number;
  passRate: number;
  averageScore: number;
  averageHints: number;
}

export interface QuizPerformance {
  quizId: string;
  quizTitle: string;
  attempts: number;
  averageScore: number;
  passRate: number;
}

export interface AnalyticsReport {
  overview: PlatformOverview;
  courses: CoursePerformance[];
  labs: LabPerformance[];
  quizzes: QuizPerformance[];
}

export interface RosterEntry {
  userId: string;
  displayName: string;
  email: string;
  level: number;
  totalXp: number;
  lessonsCompleted: number;
  labsCompleted: number;
  lastActiveAt: string | null;
}

export const adminApi = {
  analytics: () => apiClient.get<AnalyticsReport>('/admin/analytics'),
  roster: () => apiClient.get<RosterEntry[]>('/admin/roster'),
};
