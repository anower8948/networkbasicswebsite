import { zodResolver } from '@hookform/resolvers/zod';
import { AtSign, Eye, EyeOff, Lock, User as UserIcon } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/features/auth/hooks/use-auth';
import {
  passwordStrength,
  registerSchema,
  type RegisterFormValues,
} from '@/features/auth/schemas';
import { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/cn';

const STRENGTH_LABELS = ['Too weak', 'Weak', 'Fair', 'Good', 'Strong'] as const;
const STRENGTH_COLORS = [
  'bg-[var(--color-danger)]',
  'bg-[var(--color-danger)]',
  'bg-[var(--color-warning)]',
  'bg-[var(--color-info)]',
  'bg-[var(--color-success)]',
] as const;

/** Visual feedback on password quality — advisory only, never blocking. */
function PasswordStrengthMeter({ password }: { password: string }) {
  const score = passwordStrength(password);
  if (!password) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex gap-1" aria-hidden>
        {[0, 1, 2, 3].map((index) => (
          <span
            key={index}
            className={cn(
              'h-1 flex-1 rounded-full transition-colors duration-[var(--duration-base)]',
              index < score ? STRENGTH_COLORS[score] : 'bg-[var(--hairline)]',
            )}
          />
        ))}
      </div>
      <p className="text-[12px] text-[var(--text-tertiary)]">
        Password strength: {STRENGTH_LABELS[score]}
      </p>
    </div>
  );
}

export function RegisterForm() {
  const { register: registerAccount } = useAuth();
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { fullName: '', username: '', email: '', password: '', confirmPassword: '' },
  });

  const password = watch('password');

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await registerAccount({
        email: values.email,
        username: values.username,
        password: values.password,
        ...(values.fullName ? { fullName: values.fullName } : {}),
      });
      void navigate('/dashboard', { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        // The server owns uniqueness; surface those conflicts on the field
        // that caused them rather than as a generic banner.
        if (error.code === 'email_already_registered') {
          setError('email', { message: 'An account with this email already exists.' });
          return;
        }
        if (error.code === 'username_already_taken') {
          setError('username', { message: 'This username is taken.' });
          return;
        }

        const entries = Object.entries(error.fieldErrors);
        if (entries.length > 0) {
          for (const [field, message] of entries) {
            if (field === 'email' || field === 'username' || field === 'password') {
              setError(field, { message });
            }
          }
          return;
        }
        setFormError(error.message);
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
        {...register('fullName')}
        label="Full name"
        placeholder="Ada Lovelace"
        autoComplete="name"
        hint="Optional — shown on your certificates."
        leadingIcon={<UserIcon className="size-4" />}
        error={errors.fullName?.message}
      />

      <Input
        {...register('username')}
        label="Username"
        placeholder="ada"
        autoComplete="username"
        leadingIcon={<UserIcon className="size-4" />}
        error={errors.username?.message}
      />

      <Input
        {...register('email')}
        type="email"
        label="Email"
        placeholder="you@example.com"
        autoComplete="email"
        leadingIcon={<AtSign className="size-4" />}
        error={errors.email?.message}
      />

      <div className="flex flex-col gap-2">
        <Input
          {...register('password')}
          type={showPassword ? 'text' : 'password'}
          label="Password"
          placeholder="At least 10 characters"
          autoComplete="new-password"
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
        <PasswordStrengthMeter password={password} />
      </div>

      <Input
        {...register('confirmPassword')}
        type={showPassword ? 'text' : 'password'}
        label="Confirm password"
        placeholder="Re-enter your password"
        autoComplete="new-password"
        leadingIcon={<Lock className="size-4" />}
        error={errors.confirmPassword?.message}
      />

      <Button type="submit" size="lg" fullWidth isLoading={isSubmitting} className="mt-2">
        {isSubmitting ? 'Creating account' : 'Create account'}
      </Button>
    </form>
  );
}
