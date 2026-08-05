import { cn } from '@/lib/cn';

/**
 * The platform mark: three nodes joined by links — a network in miniature.
 *
 * Drawn inline as SVG rather than shipped as an asset so it inherits
 * `currentColor` and stays crisp at every size without a sprite request.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={cn('size-8', className)} aria-hidden>
      <defs>
        <linearGradient id="nlp-logo-gradient" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="oklch(0.68 0.16 235)" />
          <stop offset="55%" stopColor="oklch(0.62 0.19 255)" />
          <stop offset="100%" stopColor="oklch(0.66 0.19 300)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#nlp-logo-gradient)" />
      <g stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.95">
        <path d="M10.5 11.5 L21.5 11.5" />
        <path d="M10.5 11.5 L10.5 20.5" />
        <path d="M21.5 11.5 L21.5 20.5" />
        <path d="M10.5 20.5 L21.5 20.5" />
      </g>
      <g fill="white">
        <circle cx="10.5" cy="11.5" r="2.6" />
        <circle cx="21.5" cy="11.5" r="2.6" />
        <circle cx="10.5" cy="20.5" r="2.6" />
        <circle cx="21.5" cy="20.5" r="2.6" />
      </g>
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <Logo />
      <span className="text-title text-[15px] leading-tight font-semibold">
        Network
        <span className="text-[var(--text-tertiary)] font-normal"> Learning</span>
      </span>
    </span>
  );
}
