import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { Alert } from '@/components/ui/alert';
import { Avatar } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SectionCard } from '@/components/ui/section-card';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { profileApi } from '@/features/profile/api/profile-api';
import { ApiError } from '@/lib/api-client';
import type { ProfileUpdatePayload } from '@/types/api';

const schema = z.object({
  fullName: z.string().max(120, 'Use at most 120 characters.'),
  bio: z.string().max(2000, 'Use at most 2000 characters.'),
  country: z
    .string()
    .max(2, 'Use a two-letter country code.')
    .regex(/^[A-Za-z]*$/, 'Use letters only.'),
  avatarUrl: z.string().max(512).url('Enter a valid URL.').or(z.literal('')),
});

type FormValues = z.infer<typeof schema>;

export function ProfileForm() {
  const { user, setUser } = useAuth();
  const [saved, setSaved] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      fullName: user?.fullName ?? '',
      bio: user?.bio ?? '',
      country: user?.country ?? '',
      avatarUrl: user?.avatarUrl ?? '',
    },
  });

  const save = useMutation({
    mutationFn: (payload: ProfileUpdatePayload) => profileApi.update(payload),
    onSuccess: (updated) => {
      setUser(updated);
      setSaved(true);
    },
  });

  const onSubmit = handleSubmit((values) => {
    setSaved(false);
    // Empty strings mean "cleared", which the API expresses as null.
    save.mutate({
      fullName: values.fullName || null,
      bio: values.bio || null,
      country: values.country ? values.country.toUpperCase() : null,
      avatarUrl: values.avatarUrl || null,
    });
  });

  const previewName = watch('fullName') || user?.username || '';
  const previewAvatar = watch('avatarUrl');

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate>
      <SectionCard
        title="Profile"
        description="This is how you appear on certificates and leaderboards."
        footer={
          <div className="flex items-center justify-between gap-3">
            <span className="text-[13px] text-[var(--text-tertiary)]">
              {saved && !isDirty ? 'All changes saved.' : 'Changes are saved when you submit.'}
            </span>
            <Button type="submit" isLoading={save.isPending}>
              Save changes
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-5">
          {save.error instanceof ApiError && (
            <Alert tone="danger">{save.error.message}</Alert>
          )}
          {saved && !save.isPending && <Alert tone="success">Your profile was updated.</Alert>}

          <div className="flex items-center gap-4">
            <Avatar name={previewName} imageUrl={previewAvatar} size="lg" />
            <div className="min-w-0">
              <p className="text-sm font-medium">{previewName}</p>
              <p className="truncate text-[13px] text-[var(--text-tertiary)]">
                {user?.email}
              </p>
            </div>
          </div>

          <Input
            {...register('fullName')}
            label="Full name"
            placeholder="Ada Lovelace"
            autoComplete="name"
            error={errors.fullName?.message}
          />

          <Input
            {...register('avatarUrl')}
            label="Avatar URL"
            placeholder="https://example.com/photo.jpg"
            hint="Leave blank to use your initials."
            error={errors.avatarUrl?.message}
          />

          <Input
            {...register('country')}
            label="Country code"
            placeholder="GB"
            maxLength={2}
            hint="Two-letter ISO code, shown on leaderboards."
            error={errors.country?.message}
          />

          <div className="flex w-full flex-col gap-1.5">
            <label
              htmlFor="profile-bio"
              className="text-[13px] font-medium text-[var(--text-secondary)]"
            >
              Bio
            </label>
            <textarea
              {...register('bio')}
              id="profile-bio"
              rows={4}
              placeholder="What are you working toward?"
              className="glass-inset w-full resize-y rounded-[var(--radius-sm)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-accent-500 focus:outline-none"
            />
            {errors.bio?.message && (
              <p role="alert" className="text-[13px] text-[var(--color-danger)]">
                {errors.bio.message}
              </p>
            )}
          </div>
        </div>
      </SectionCard>
    </form>
  );
}
