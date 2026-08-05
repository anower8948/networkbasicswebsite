/** Profile and progress endpoints. */

import { apiClient } from '@/lib/api-client';
import type { MessageResponse, ProfileUpdatePayload, ProgressSummary, User } from '@/types/api';

export const profileApi = {
  me: () => apiClient.get<User>('/users/me'),

  update: (payload: ProfileUpdatePayload) => apiClient.patch<User>('/users/me', payload),

  progress: () => apiClient.get<ProgressSummary>('/users/me/progress'),

  /**
   * Report study time. Returns the refreshed summary, so a streak increment or
   * level-up lands without a follow-up request.
   */
  recordActivity: (studySeconds: number) =>
    apiClient.post<ProgressSummary>('/users/me/activity', { studySeconds }),

  deactivate: () => apiClient.post<MessageResponse>('/users/me/deactivate'),
};
