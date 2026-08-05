/** Achievements, leaderboards, and certificates. */

import { apiClient } from '@/lib/api-client';
import type {
  AchievementList,
  Certificate,
  CertificateVerification,
  Leaderboard,
  LeaderboardScope,
} from '@/types/gamification';

export const gamificationApi = {
  achievements: () => apiClient.get<AchievementList>('/achievements'),

  /** Re-checks every badge. Idempotent, so calling it is always safe. */
  evaluateAchievements: () => apiClient.post<AchievementList>('/achievements/evaluate'),

  leaderboard: (scope: LeaderboardScope) =>
    apiClient.get<Leaderboard>(`/leaderboard?scope=${scope}`),

  certificates: () => apiClient.get<Certificate[]>('/certificates'),

  claimCertificate: (courseSlug: string) =>
    apiClient.post<Certificate>(`/certificates/${courseSlug}`),

  /** Public — no session required, which is the point of a verification code. */
  verifyCertificate: (code: string) =>
    apiClient.get<CertificateVerification>(`/certificates/verify/${code}`),
};
