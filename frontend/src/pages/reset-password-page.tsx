import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Eye, EyeOff, Lock } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { AuthLayout } from '@/components/layout/auth-layout';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { authApi } from '@/features/auth/api/auth-api';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { passwordSchema } from '@/features/auth/schemas';
import { ApiError } from '@/lib/api-client';
import type { PasswordResetPayload } from '@/types/api';

const schema = z
  .object({
    newPassword: passwordSchema,
    confirmPassword: z.string().min(1, 'Confirm your password.'),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: 'Passwords do not match.',
    path: ['confirmPassword'],
  });

type FormValues = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { newPassword: '', confirmPassword: '' },
  });

  const { isAuthenticated, logout } = useAuth();

  const reset = useMutation({
    mutationFn: (payload: PasswordResetPayload) => authApi.resetPassword(payload),
    onSuccess: () => {
      // The server revoked every session, including this browser's. Clear the
      // local one too, or the UI would keep showing a signed-in shell backed by
      // an access token that 401s on its next use.
      if (isAuthenticated) void logout();
    },
  });

  const onSubmit = handleSubmit((values) => {
    if (!token) return;
    reset.mutate({ token, newPassword: values.newPassword });
  });

  if (!token) {
    return (
      <AuthLayout
        title="Invalid reset link"
        subtitle="This address is missing its reset token."
        footer={
          <Link
            to="/forgot-password"
            className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
          >
            Request a new link
          </Link>
        }
      >
        <Alert tone="danger">
          Open the link exactly as it appears in your email, or request a fresh one.
        </Alert>
      </AuthLayout>
    );
  }

  if (reset.isSuccess) {
    return (
      <AuthLayout
        title="Password updated"
        subtitle="Every device has been signed out."
        footer={
          <Link
            to="/login"
            className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
          >
            Sign in
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <CheckCircle2 className="size-11 text-[var(--color-success)]" aria-hidden />
          <p className="text-sm text-[var(--text-secondary)]">
            Sign in with your new password to continue.
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="This will sign you out of every device."
      footer={
        <Link
          to="/login"
          className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
        >
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={(event) => void onSubmit(event)} noValidate className="flex flex-col gap-4">
        {reset.error instanceof ApiError && (
          <Alert tone="danger">
            {reset.error.status === 401
              ? 'This link has expired or was already used. Request a new one.'
              : reset.error.message}
          </Alert>
        )}

        <Input
          {...register('newPassword')}
          type={showPassword ? 'text' : 'password'}
          label="New password"
          placeholder="At least 10 characters"
          autoComplete="new-password"
          autoFocus
          leadingIcon={<Lock className="size-4" />}
          error={errors.newPassword?.message}
          trailingSlot={
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="inline-flex size-8 items-center justify-center rounded-[var(--radius-xs)] text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)]"
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          }
        />

        <Input
          {...register('confirmPassword')}
          type={showPassword ? 'text' : 'password'}
          label="Confirm new password"
          placeholder="Re-enter your password"
          autoComplete="new-password"
          leadingIcon={<Lock className="size-4" />}
          error={errors.confirmPassword?.message}
        />

        <Button type="submit" size="lg" fullWidth isLoading={reset.isPending} className="mt-2">
          {reset.isPending ? 'Updating password' : 'Update password'}
        </Button>
      </form>
    </AuthLayout>
  );
}
