import { motion } from 'motion/react';
import { useSearchParams } from 'react-router-dom';

import { VerificationBanner } from '@/features/auth/components/verification-banner';
import { PreferencesSection } from '@/features/profile/components/preferences-section';
import { ProfileForm } from '@/features/profile/components/profile-form';
import { SecuritySection } from '@/features/profile/components/security-section';
import { cn } from '@/lib/cn';

const TABS = [
  { id: 'profile', label: 'Profile' },
  { id: 'security', label: 'Security' },
  { id: 'preferences', label: 'Preferences' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export default function SettingsPage() {
  // The active tab lives in the URL so a section can be linked to and survives
  // a reload — "?tab=security" is a shareable, bookmarkable address.
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const active: TabId = TABS.some((tab) => tab.id === requested)
    ? (requested as TabId)
    : 'profile';

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-display text-[26px] leading-tight font-semibold">Account settings</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage your profile, security, and preferences.
        </p>
      </header>

      <VerificationBanner />

      <div
        role="tablist"
        aria-label="Settings sections"
        className="glass-inset inline-flex w-fit gap-0.5 rounded-[var(--radius-md)] p-1"
      >
        {TABS.map((tab) => {
          const isActive = tab.id === active;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              id={`tab-${tab.id}`}
              onClick={() => setSearchParams({ tab: tab.id }, { replace: true })}
              className={cn(
                'rounded-[var(--radius-sm)] px-4 py-2 text-sm font-medium',
                'transition-all duration-[var(--duration-fast)]',
                isActive
                  ? 'bg-[var(--surface-raised)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <motion.div
        // Re-keying on the tab replays the entrance, so switching sections reads
        // as a transition rather than an instant swap.
        key={active}
        id={`panel-${active}`}
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      >
        {active === 'profile' && <ProfileForm />}
        {active === 'security' && <SecuritySection />}
        {active === 'preferences' && <PreferencesSection />}
      </motion.div>
    </div>
  );
}
