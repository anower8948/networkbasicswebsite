import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle } from 'lucide-react';
import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AuthLayout } from '@/components/layout/auth-layout';
import { Spinner } from '@/components/ui/spinner';
import { authApi } from '@/features/auth/api/auth-api';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { ApiError } from '@/lib/api-client';

/**
 * Lands the emailed verification link.
 *
 * Verification fires automatically on arrival rather than behind a button: the
 * user already expressed intent by clicking the link in their mail client, and
 * asking them to confirm twice is friction with no security benefit.
 *
 * Modelled as a **query keyed on the token**, not a mutation, despite changing
 * server state. Two properties make that the right choice here:
 *
 * * A mutation's state lives on the component's observer. StrictMode's
 *   simulated unmount detaches it, so the in-flight result resolves into a dead
 *   observer and the remounted one sits idle — the page spins forever.
 * * A query is cached by key, so the single-use token is spent exactly once no
 *   matter how many times this component mounts, and the outcome survives
 *   remounts without a manual "already attempted" guard.
 */
export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { user, setUser } = useAuth();

  const verify = useQuery({
    queryKey: ['verify-email', token],
    queryFn: () => authApi.verifyEmail(token as string),
    enabled: Boolean(token),
    // A consumed token cannot succeed on a retry, and re-running would report
    // "already used" for a verification that actually worked.
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  // Refresh the cached user so the warning banner clears immediately when the
  // verified account is the one currently signed in.
  const verified = verify.data;
  useEffect(() => {
    if (verified && user && user.id === verified.id && !user.isEmailVerified) {
      setUser(verified);
    }
  }, [verified, user, setUser]);

  const body = (() => {
    if (!token) {
      return {
        Icon: XCircle,
        tone: 'var(--color-danger)',
        title: 'No token in this link',
        message:
          'The address is missing its verification token. Open the link from your email exactly as sent.',
      };
    }
    if (verify.isPending) {
      return null;
    }
    if (verify.isSuccess) {
      return {
        Icon: CheckCircle2,
        tone: 'var(--color-success)',
        title: 'Email confirmed',
        message: 'Your address is verified. Certificates are now unlocked.',
      };
    }
    return {
      Icon: XCircle,
      tone: 'var(--color-danger)',
      title: 'This link did not work',
      message:
        verify.error instanceof ApiError
          ? verify.error.message
          : 'Something went wrong. Request a new link from your account settings.',
    };
  })();

  return (
    <AuthLayout
      title="Email verification"
      subtitle="Confirming the link from your inbox."
      footer={
        <Link
          to="/dashboard"
          className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
        >
          Go to dashboard
        </Link>
      }
    >
      {body === null ? (
        <div className="flex flex-col items-center gap-4 py-6">
          <Spinner size="lg" className="text-accent-500" label="Verifying" />
          <p className="text-sm text-[var(--text-secondary)]">Verifying your address…</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <body.Icon className="size-11" style={{ color: body.tone }} aria-hidden />
          <p className="text-title text-base font-semibold">{body.title}</p>
          <p className="text-sm text-[var(--text-secondary)]">{body.message}</p>
        </div>
      )}
    </AuthLayout>
  );
}
