/** Achievements, leaderboards, and certificates — mirrors `app/schemas/gamification.py`. */

export type AchievementCategory =
  | 'progress'
  | 'mastery'
  | 'streak'
  | 'lab'
  | 'community'
  | 'special';

export interface Achievement {
  id: string;
  slug: string;
  title: string;
  description: string;
  icon: string | null;
  category: AchievementCategory;
  xpReward: number;
  earned: boolean;
  earnedAt: string | null;
  progressPercent: number | null;
}

export interface AchievementList {
  items: Achievement[];
  earnedCount: number;
  totalCount: number;
}

export const CATEGORY_LABELS: Record<AchievementCategory, string> = {
  progress: 'Progress',
  mastery: 'Mastery',
  streak: 'Consistency',
  lab: 'Hands-on',
  community: 'Community',
  special: 'Special',
};

export type LeaderboardScope = 'all_time' | 'monthly' | 'weekly';

export const SCOPE_LABELS: Record<LeaderboardScope, string> = {
  all_time: 'All time',
  monthly: 'This month',
  weekly: 'This week',
};

export interface LeaderboardEntry {
  rank: number;
  userId: string;
  displayName: string;
  avatarUrl: string | null;
  countryCode: string | null;
  level: number;
  xp: number;
  isYou: boolean;
}

export interface Leaderboard {
  scope: LeaderboardScope;
  entries: LeaderboardEntry[];
  you: LeaderboardEntry | null;
}

export interface Certificate {
  id: string;
  courseId: string;
  courseTitle: string;
  serial: string;
  verificationCode: string;
  recipientName: string;
  finalScore: number | null;
  issuedAt: string;
  revokedAt: string | null;
}

export interface CertificateVerification {
  valid: boolean;
  recipientName: string | null;
  courseTitle: string | null;
  issuedAt: string | null;
  revoked: boolean;
}
