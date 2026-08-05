/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * Hand-maintained for now. Part 10 replaces this file with types generated
 * from the API's OpenAPI document, which removes the risk of drift entirely.
 */

export type UserRole = 'student' | 'instructor' | 'admin';

export interface UserStats {
  totalXp: number;
  level: number;
  lessonsCompleted: number;
  coursesCompleted: number;
  labsCompleted: number;
  quizzesPassed: number;
  totalStudySeconds: number;
  currentStreakDays: number;
  longestStreakDays: number;
}

export interface User {
  id: string;
  email: string;
  username: string;
  fullName: string | null;
  avatarUrl: string | null;
  bio: string | null;
  country: string | null;
  timezone: string;
  role: UserRole;
  isActive: boolean;
  isEmailVerified: boolean;
  createdAt: string;
  lastLoginAt: string | null;
  stats: UserStats | null;
}

export interface TokenResponse {
  accessToken: string;
  tokenType: string;
  /** Access token lifetime in seconds. */
  expiresIn: number;
  user: User;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  username: string;
  password: string;
  fullName?: string;
}

export interface ChangePasswordPayload {
  currentPassword: string;
  newPassword: string;
}

export interface ProfileUpdatePayload {
  fullName?: string | null;
  bio?: string | null;
  avatarUrl?: string | null;
  country?: string | null;
  timezone?: string;
}

/* -------------------------------------------------------------------------- */
/* Progress                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Level state, computed entirely server-side.
 *
 * The level curve lives in one place (`services/progress_service.py`). The
 * client renders these numbers and must never recompute them, or the two
 * implementations will drift and show different levels for the same XP.
 */
export interface LevelProgress {
  level: number;
  totalXp: number;
  currentLevelXp: number;
  nextLevelXp: number;
  xpIntoLevel: number;
  xpForNextLevel: number;
  percentToNextLevel: number;
  isMaxLevel: boolean;
}

export type XPReason =
  | 'lesson_completed'
  | 'quiz_passed'
  | 'lab_completed'
  | 'course_completed'
  | 'achievement_earned'
  | 'streak_bonus'
  | 'manual_adjustment';

export interface XPTransaction {
  id: string;
  amount: number;
  reason: XPReason;
  referenceType: string | null;
  referenceId: string | null;
  createdAt: string;
}

export interface ProgressSummary {
  totalXp: number;
  level: LevelProgress;
  lessonsCompleted: number;
  coursesCompleted: number;
  labsCompleted: number;
  quizzesPassed: number;
  totalStudySeconds: number;
  currentStreakDays: number;
  longestStreakDays: number;
  xpThisWeek: number;
  lastActivityAt: string | null;
  recentXp: XPTransaction[];
}

/* -------------------------------------------------------------------------- */
/* Sessions and verification                                                   */
/* -------------------------------------------------------------------------- */

export interface SessionInfo {
  id: string;
  userAgent: string | null;
  ipAddress: string | null;
  issuedAt: string;
  expiresAt: string;
  isCurrent: boolean;
}

export interface MessageResponse {
  message: string;
}

export interface PasswordResetPayload {
  token: string;
  newPassword: string;
}

/** The single error envelope every failing endpoint returns. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
