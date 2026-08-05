/** Lab library, attempts, and grading endpoints. */

import { apiClient } from '@/lib/api-client';
import type { Page } from '@/types/api';
import type {
  HintResponse,
  LabAttempt,
  LabDetail,
  LabGradeResult,
  LabSummary,
} from '@/types/lab';
import type { TopologyDocument } from '@/types/topology';

export const labApi = {
  list: () => apiClient.get<Page<LabSummary>>('/labs'),

  get: (slug: string) => apiClient.get<LabDetail>(`/labs/${slug}`),

  /** Starts a new attempt, or resumes the one already open. */
  startAttempt: (slug: string) => apiClient.post<LabAttempt>(`/labs/${slug}/attempts`),

  saveTopology: (attemptId: string, document: TopologyDocument, timeSpentSeconds: number) =>
    apiClient.put<LabAttempt>(`/labs/attempts/${attemptId}/topology`, {
      document,
      timeSpentSeconds,
    }),

  /** Formative: grades without closing the attempt. */
  check: (attemptId: string) =>
    apiClient.post<LabGradeResult>(`/labs/attempts/${attemptId}/check`),

  /** Final: closes the attempt and awards XP. */
  submit: (attemptId: string) =>
    apiClient.post<LabGradeResult>(`/labs/attempts/${attemptId}/submit`),

  hint: (attemptId: string, objectiveId: string) =>
    apiClient.post<HintResponse>(`/labs/attempts/${attemptId}/hint`, { objectiveId }),
};
