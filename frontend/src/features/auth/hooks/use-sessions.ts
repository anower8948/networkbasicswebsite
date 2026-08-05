import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { authApi } from '@/features/auth/api/auth-api';
import { queryKeys } from '@/lib/query-client';

/** Devices holding a live refresh token. */
export function useSessions() {
  return useQuery({
    queryKey: queryKeys.sessions,
    queryFn: authApi.sessions,
    // Revoking elsewhere should show up reasonably promptly on this screen.
    staleTime: 10_000,
  });
}

export function useRevokeSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) => authApi.revokeSession(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });
}
