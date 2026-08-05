import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { profileApi } from '@/features/profile/api/profile-api';
import { queryKeys } from '@/lib/query-client';
import type { ProgressSummary } from '@/types/api';

/** The dashboard's progress summary. */
export function useProgress() {
  return useQuery({
    queryKey: queryKeys.progress,
    queryFn: profileApi.progress,
  });
}

/**
 * Reports study time to the server.
 *
 * The response is written straight into the cache rather than triggering a
 * refetch — the endpoint already returns the updated summary, so a second round
 * trip would only add latency and a visible flicker.
 */
export function useRecordActivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (studySeconds: number) => profileApi.recordActivity(studySeconds),
    onSuccess: (summary: ProgressSummary) => {
      queryClient.setQueryData(queryKeys.progress, summary);
    },
  });
}
