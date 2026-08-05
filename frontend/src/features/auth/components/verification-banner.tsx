import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { authApi } from '@/features/auth/api/auth-api';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { ApiError } from '@/lib/api-client';

/**
 * Prompts an unverified user to confirm their address.
 *
 * Deliberately non-blocking: an unverified account can still learn, so this is
 * a reminder rather than a gate. Verification is required only for certificates.
 */
export function VerificationBanner() {
  const { user } = useAuth();
  const [sent, setSent] = useState(false);

  const resend = useMutation({
    mutationFn: authApi.resendVerification,
    onSuccess: () => setSent(true),
  });

  if (!user || user.isEmailVerified) return null;

  if (sent) {
    return (
      <Alert tone="success" title="Verification email sent">
        Check <strong>{user.email}</strong> for the confirmation link.
      </Alert>
    );
  }

  return (
    <Alert
      tone="warning"
      title="Confirm your email address"
      action={
        <Button
          size="sm"
          variant="secondary"
          isLoading={resend.isPending}
          onClick={() => resend.mutate()}
        >
          Resend
        </Button>
      }
    >
      {resend.error instanceof ApiError && resend.error.status === 429
        ? 'Too many requests — please wait a few minutes before trying again.'
        : `We sent a link to ${user.email}. Confirm it to unlock certificates.`}
    </Alert>
  );
}
