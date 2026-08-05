/**
 * Session state for the whole application.
 *
 * On mount the provider attempts one silent refresh. That call is what restores
 * a session across a page reload: the access token only ever lived in memory,
 * but the httpOnly refresh cookie survives, so the server can mint a new pair.
 * Until it settles, `isInitialising` is true and the router shows a splash
 * rather than bouncing an authenticated user to the login page.
 */

import { useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { authApi } from '@/features/auth/api/auth-api';
import {
  setAccessToken,
  setSessionExpiredHandler,
  refreshSession,
} from '@/lib/api-client';
import type { LoginPayload, RegisterPayload, TokenResponse, User } from '@/types/api';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  /** True until the initial silent-refresh attempt has resolved. */
  isInitialising: boolean;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [isInitialising, setIsInitialising] = useState(true);
  const queryClient = useQueryClient();

  // Guards against React 18/19 StrictMode double-invoking the effect, which
  // would fire two refreshes and trip server-side reuse detection.
  const bootstrapped = useRef(false);

  const applySession = useCallback((response: TokenResponse): User => {
    setAccessToken(response.accessToken);
    setUserState(response.user);
    return response.user;
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUserState(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    // The ref already ensures this runs exactly once, so there is deliberately
    // no cleanup flag: under StrictMode the first mount's cleanup would cancel
    // the only run in flight while the second mount is short-circuited by the
    // ref, leaving `isInitialising` stuck true and the app on its splash screen
    // forever. Setting state after unmount is a harmless no-op in React 18+.
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    void (async () => {
      try {
        if (await refreshSession()) {
          setUserState(await authApi.me());
        }
      } catch {
        clearSession();
      } finally {
        setIsInitialising(false);
      }
    })();
  }, [clearSession]);

  // The API client calls this when a request 401s and refresh cannot recover.
  useEffect(() => {
    setSessionExpiredHandler(clearSession);
    return () => setSessionExpiredHandler(null);
  }, [clearSession]);

  const login = useCallback(
    async (payload: LoginPayload) => applySession(await authApi.login(payload)),
    [applySession],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => applySession(await authApi.register(payload)),
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      // Clear locally even if the network call failed — the user asked to be
      // signed out, and the cookie is dead either way on the next refresh.
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: user !== null,
      isInitialising,
      login,
      register,
      logout,
      setUser: setUserState,
    }),
    [user, isInitialising, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
