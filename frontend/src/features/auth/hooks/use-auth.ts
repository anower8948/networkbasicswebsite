import { useContext } from 'react';

import { AuthContext } from '@/providers/auth-provider';

/** Access the current session. Throws if used outside `AuthProvider`. */
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return context;
}
