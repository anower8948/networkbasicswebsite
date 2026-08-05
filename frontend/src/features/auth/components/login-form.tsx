import { zodResolver } from '@hookform/resolvers/zod';
import { AtSign, Eye, EyeOff, Lock } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { loginSchema, type LoginFormValues } from '@/features/auth/schemas';
import { ApiError } from '@/lib/api-client';

export function LoginForm() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  // Where the user was heading before the guard bounced them here.
  const redirectTo =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/dashboard';

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values);
      void navigate(redirectTo, { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        // Map server-side field errors onto the matching inputs; anything
        // without a field (bad credentials) becomes a form-level message.
        const fields = error.fieldErrors;
        const entries = Object.entries(fields);
        if (entries.length > 0) {
          for (const [field, message] of entries) {
            if (field === 'email' || field === 'password') {
              setError(field, { message });
            }
          }
        } else {
          setFormError(error.message);
        }
      } else {
        setFormError('Could not reach the server. Check your connection and try again.');
      }
    }
  });

  // `handleSubmit` returns a promise, but a DOM submit handler must return void.
  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate className="flex flex-col gap-4">
      {formError && (
        <p
          role="alert"
          className="rounded-[var(--radius-sm)] border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3.5 py-2.5 text-[13px] text-[var(--color-danger)]"
        >
          {formError}
        </p>
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

      <Input
        {...register('password')}
        type={showPassword ? 'text' : 'password'}
        label="Password"
        placeholder="••••••••••"
        autoComplete="current-password"
        leadingIcon={<Lock className="size-4" />}
        error={errors.password?.message}
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

      <div className="-mt-1 flex justify-end">
        <Link
          to="/forgot-password"
          className="text-[13px] text-[var(--text-secondary)] transition-colors hover:text-accent-600 dark:hover:text-accent-400"
        >
          Forgot your password?
        </Link>
      </div>

      <Button type="submit" size="lg" fullWidth isLoading={isSubmitting} className="mt-1">
        {isSubmitting ? 'Signing in' : 'Sign in'}
      </Button>
    </form>
  );
}
