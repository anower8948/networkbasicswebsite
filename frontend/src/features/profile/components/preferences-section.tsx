import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { SectionCard } from '@/components/ui/section-card';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { useAuth } from '@/features/auth/hooks/use-auth';
import { profileApi } from '@/features/profile/api/profile-api';
import { ApiError } from '@/lib/api-client';

/**
 * Timezones offered in the picker.
 *
 * A short curated list rather than the full IANA database: the value only
 * affects which calendar day a study session counts toward, so offset coverage
 * matters far more than exhaustiveness. The API validates any value, so an
 * unlisted zone can still be set through it.
 */
const TIMEZONES = [
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Moscow',
  'Africa/Lagos',
  'Africa/Nairobi',
  'Asia/Dubai',
  'Asia/Karachi',
  'Asia/Dhaka',
  'Asia/Kolkata',
  'Asia/Bangkok',
  'Asia/Singapore',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Australia/Sydney',
  'America/Sao_Paulo',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
] as const;

function TimezoneCard() {
  const { user, setUser } = useAuth();
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (timezone: string) => profileApi.update({ timezone }),
    onSuccess: (updated) => {
      setUser(updated);
      setSaved(true);
    },
  });

  return (
    <SectionCard
      title="Timezone"
      description="Study streaks are counted in calendar days in this timezone."
    >
      <div className="flex flex-col gap-4">
        {saved && <Alert tone="success">Timezone updated.</Alert>}
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}

        <div className="flex w-full flex-col gap-1.5">
          <label
            htmlFor="timezone-select"
            className="text-[13px] font-medium text-[var(--text-secondary)]"
          >
            Your timezone
          </label>
          <select
            id="timezone-select"
            value={user?.timezone ?? 'UTC'}
            onChange={(event) => {
              setSaved(false);
              save.mutate(event.target.value);
            }}
            disabled={save.isPending}
            className="glass-inset h-11 w-full rounded-[var(--radius-sm)] px-3 text-sm text-[var(--text-primary)] focus:border-accent-500 focus:outline-none"
          >
            {/* Include the stored value even when it is not in the curated list,
                or the picker would silently misreport the user's setting. */}
            {user?.timezone && !TIMEZONES.includes(user.timezone as (typeof TIMEZONES)[number]) && (
              <option value={user.timezone}>{user.timezone}</option>
            )}
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>
    </SectionCard>
  );
}

function AppearanceCard() {
  return (
    <SectionCard title="Appearance" description="Choose light, dark, or follow your system.">
      <ThemeToggle />
    </SectionCard>
  );
}

function DangerZoneCard() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  const deactivate = useMutation({
    mutationFn: profileApi.deactivate,
    onSuccess: async () => {
      await logout();
      void navigate('/login', { replace: true });
    },
  });

  return (
    <SectionCard
      title="Deactivate account"
      description="Your progress, certificates and saved work are preserved, but you will not be able to sign in."
    >
      <div className="flex flex-col gap-4">
        {deactivate.error instanceof ApiError && (
          <Alert tone="danger">{deactivate.error.message}</Alert>
        )}

        {confirming ? (
          // A two-step confirmation, because this action locks the user out and
          // they cannot undo it themselves.
          <Alert tone="danger" title="Are you sure?">
            <p className="mb-3">
              You will be signed out immediately and will need an administrator to restore
              access.
            </p>
            <div className="flex gap-2">
              <Button
                variant="danger"
                size="sm"
                isLoading={deactivate.isPending}
                onClick={() => deactivate.mutate()}
              >
                Yes, deactivate
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          </Alert>
        ) : (
          <div>
            <Button variant="danger" onClick={() => setConfirming(true)}>
              Deactivate my account
            </Button>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

export function PreferencesSection() {
  return (
    <div className="flex flex-col gap-5">
      <AppearanceCard />
      <TimezoneCard />
      <DangerZoneCard />
    </div>
  );
}
