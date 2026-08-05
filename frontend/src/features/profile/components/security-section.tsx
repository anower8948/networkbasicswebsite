import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { Laptop, Lock, Smartphone, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SectionCard } from '@/components/ui/section-card';
import { Spinner } from '@/components/ui/spinner';
import { authApi } from '@/features/auth/api/auth-api';
import { useRevokeSession, useSessions } from '@/features/auth/hooks/use-sessions';
import { passwordSchema } from '@/features/auth/schemas';
import { ApiError, setAccessToken } from '@/lib/api-client';
import type { ChangePasswordPayload, SessionInfo } from '@/types/api';

const passwordFormSchema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password.'),
    newPassword: passwordSchema,
    confirmPassword: z.string().min(1, 'Confirm your new password.'),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: 'Passwords do not match.',
    path: ['confirmPassword'],
  });

type PasswordFormValues = z.infer<typeof passwordFormSchema>;

function ChangePasswordCard() {
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(passwordFormSchema),
    defaultValues: { currentPassword: '', newPassword: '', confirmPassword: '' },
  });

  const change = useMutation({
    mutationFn: (payload: ChangePasswordPayload) => authApi.changePassword(payload),
    onSuccess: (tokens) => {
      // The server rotates tokens and revokes other sessions; adopt the new
      // access token or every subsequent request would 401.
      setAccessToken(tokens.accessToken);
      setDone(true);
      reset();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        setError('currentPassword', { message: 'That password is not correct.' });
      }
    },
  });

  const onSubmit = handleSubmit((values) => {
    setDone(false);
    change.mutate({
      currentPassword: values.currentPassword,
      newPassword: values.newPassword,
    });
  });

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate>
      <SectionCard
        title="Password"
        description="Changing your password signs out every other device."
        footer={
          <div className="flex justify-end">
            <Button type="submit" isLoading={change.isPending}>
              Update password
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          {done && <Alert tone="success">Your password was changed.</Alert>}
          {change.error instanceof ApiError && change.error.status !== 401 && (
            <Alert tone="danger">{change.error.message}</Alert>
          )}

          <Input
            {...register('currentPassword')}
            type="password"
            label="Current password"
            autoComplete="current-password"
            leadingIcon={<Lock className="size-4" />}
            error={errors.currentPassword?.message}
          />
          <Input
            {...register('newPassword')}
            type="password"
            label="New password"
            autoComplete="new-password"
            leadingIcon={<Lock className="size-4" />}
            error={errors.newPassword?.message}
          />
          <Input
            {...register('confirmPassword')}
            type="password"
            label="Confirm new password"
            autoComplete="new-password"
            leadingIcon={<Lock className="size-4" />}
            error={errors.confirmPassword?.message}
          />
        </div>
      </SectionCard>
    </form>
  );
}

/** Best-effort device label from the user agent — informational only. */
function describeDevice(userAgent: string | null): { label: string; isMobile: boolean } {
  if (!userAgent) return { label: 'Unknown device', isMobile: false };

  const isMobile = /iphone|ipad|android|mobile/i.test(userAgent);
  const browser =
    /edg\//i.test(userAgent) ? 'Edge'
    : /chrome|crios/i.test(userAgent) ? 'Chrome'
    : /firefox|fxios/i.test(userAgent) ? 'Firefox'
    : /safari/i.test(userAgent) ? 'Safari'
    : 'Browser';
  const platform =
    /iphone|ipad/i.test(userAgent) ? 'iOS'
    : /android/i.test(userAgent) ? 'Android'
    : /mac os/i.test(userAgent) ? 'macOS'
    : /windows/i.test(userAgent) ? 'Windows'
    : /linux/i.test(userAgent) ? 'Linux'
    : 'Unknown OS';

  return { label: `${browser} on ${platform}`, isMobile };
}

function SessionRow({ session }: { session: SessionInfo }) {
  const revoke = useRevokeSession();
  const { label, isMobile } = describeDevice(session.userAgent);
  const Icon = isMobile ? Smartphone : Laptop;

  return (
    <li className="flex items-center gap-3 py-3">
      <Icon className="size-[18px] shrink-0 text-[var(--text-tertiary)]" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {label}
          {session.isCurrent && (
            <span className="ml-2 rounded-full bg-[var(--color-success)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]">
              This device
            </span>
          )}
        </p>
        <p className="text-[12px] text-[var(--text-tertiary)]">
          {session.ipAddress ?? 'Unknown IP'} · signed in{' '}
          {new Date(session.issuedAt).toLocaleString()}
        </p>
      </div>
      {!session.isCurrent && (
        <Button
          size="sm"
          variant="ghost"
          isLoading={revoke.isPending}
          onClick={() => revoke.mutate(session.id)}
          aria-label={`Revoke session on ${label}`}
        >
          <Trash2 className="size-4" />
        </Button>
      )}
    </li>
  );
}

function SessionsCard() {
  const { data: sessions, isLoading, error } = useSessions();

  return (
    <SectionCard
      title="Active sessions"
      description="Devices currently signed in to your account."
    >
      {isLoading ? (
        <div className="flex justify-center py-6">
          <Spinner label="Loading sessions" />
        </div>
      ) : error ? (
        <Alert tone="danger">Could not load your sessions.</Alert>
      ) : !sessions || sessions.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No active sessions.</p>
      ) : (
        <ul className="divide-y divide-[var(--hairline)]">
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function SecuritySection() {
  return (
    <div className="flex flex-col gap-5">
      <ChangePasswordCard />
      <SessionsCard />
    </div>
  );
}
