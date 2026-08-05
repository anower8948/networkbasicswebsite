/** Thin, typed wrappers around the authentication endpoints. */

import { apiClient } from '@/lib/api-client';
import type {
  ChangePasswordPayload,
  LoginPayload,
  MessageResponse,
  PasswordResetPayload,
  RegisterPayload,
  SessionInfo,
  TokenResponse,
  User,
} from '@/types/api';

export const authApi = {
  register: (payload: RegisterPayload) =>
    apiClient.post<TokenResponse>('/auth/register', payload, { skipAuthRetry: true }),

  login: (payload: LoginPayload) =>
    apiClient.post<TokenResponse>('/auth/login', payload, { skipAuthRetry: true }),

  /** Idempotent — safe to call with no active session. */
  logout: () =>
    apiClient.post<MessageResponse>('/auth/logout', undefined, { skipAuthRetry: true }),

  logoutEverywhere: () => apiClient.post<MessageResponse>('/auth/logout-all'),

  me: () => apiClient.get<User>('/auth/me'),

  changePassword: (payload: ChangePasswordPayload) =>
    apiClient.post<TokenResponse>('/auth/change-password', payload),

  /* ---- Email verification ------------------------------------------- */

  /** Unauthenticated: the token from the emailed link is the proof. */
  verifyEmail: (token: string) =>
    apiClient.post<User>('/auth/verify-email', { token }, { skipAuthRetry: true }),

  resendVerification: () => apiClient.post<MessageResponse>('/auth/resend-verification'),

  /* ---- Password reset ------------------------------------------------ */

  /** Always resolves successfully, whether or not the address is registered. */
  forgotPassword: (email: string) =>
    apiClient.post<MessageResponse>('/auth/forgot-password', { email }, { skipAuthRetry: true }),

  resetPassword: (payload: PasswordResetPayload) =>
    apiClient.post<MessageResponse>('/auth/reset-password', payload, { skipAuthRetry: true }),

  /* ---- Sessions ------------------------------------------------------ */

  sessions: () => apiClient.get<SessionInfo[]>('/auth/sessions'),

  revokeSession: (sessionId: string) =>
    apiClient.delete<MessageResponse>(`/auth/sessions/${sessionId}`),
};
