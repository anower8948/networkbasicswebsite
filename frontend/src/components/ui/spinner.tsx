import { cn } from '@/lib/cn';

const SIZES = { sm: 'size-4', md: 'size-6', lg: 'size-9' } as const;

interface SpinnerProps {
  size?: keyof typeof SIZES;
  className?: string;
  label?: string;
}

/** An indeterminate progress indicator with an accessible label. */
export function Spinner({ size = 'md', className, label = 'Loading' }: SpinnerProps) {
  return (
    <span role="status" aria-label={label} className={cn('inline-flex', className)}>
      <svg className={cn('animate-spin', SIZES[size])} viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
        <path
          d="M22 12a10 10 0 0 0-10-10"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

/** Full-viewport loader shown while the session is being restored. */
export function FullPageSpinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <Spinner size="lg" className="text-accent-500" label={label} />
      <p className="text-sm text-[var(--text-tertiary)]">{label}…</p>
    </div>
  );
}
