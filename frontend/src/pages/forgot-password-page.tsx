import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { AtSign, MailCheck } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router-dom';
import { z } from 'zod';

import { AuthLayout } from '@/components/layout/auth-layout';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { authApi } from '@/features/auth/api/auth-api';
import { ApiError } from '@/lib/api-client';

const schema = z.object({
  email: z.string().min(1, 'Enter your email address.').email('Enter a valid email address.'),
});

type FormValues = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '' },
  });

  const request = useMutation({
    mutationFn: (email: string) => authApi.forgotPassword(email),
  });

  const onSubmit = handleSubmit((values) => request.mutate(values.email));

  // The server never reveals whether the address exists, so the confirmation is
  // deliberately worded to cover both cases.
  if (request.isSuccess) {
    return (
      <AuthLayout
        title="Check your inbox"
        subtitle="If that address has an account, a reset link is on its way."
        footer={
          <Link
            to="/login"
            className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
          >
            Back to sign in
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <MailCheck className="size-11 text-[var(--color-success)]" aria-hidden />
          <p className="text-sm text-[var(--text-secondary)]">
            We sent a reset link to <strong>{getValues('email')}</strong> if an account exists
            there. The link expires in 30 minutes.
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link to choose a new password."
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
        {request.error instanceof ApiError && (
          <Alert tone={request.error.status === 429 ? 'warning' : 'danger'}>
            {request.error.status === 429
              ? 'Too many requests. Please wait a few minutes before trying again.'
              : request.error.message}
          </Alert>
        )}

        <Input
          {...register('email')}
          type="email"
          label="Email"
          placeholder="you@example.com"
          autoComplete="email"
          autoFocus
          leadingIcon={<AtSign className="size-4" />}
          error={errors.email?.message}
        />

        <Button type="submit" size="lg" fullWidth isLoading={request.isPending} className="mt-2">
          {request.isPending ? 'Sending link' : 'Send reset link'}
        </Button>
      </form>
    </AuthLayout>
  );
}
