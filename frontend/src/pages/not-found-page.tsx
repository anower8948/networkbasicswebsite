import { Link } from 'react-router-dom';

import { GlassPanel } from '@/components/ui/glass-panel';

export default function NotFoundPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center px-5">
      <GlassPanel material="strong" radius="2xl" className="max-w-md p-10 text-center">
        <p className="text-display text-6xl font-semibold text-accent-500">404</p>
        <h1 className="text-title mt-4 text-xl font-semibold">This route does not resolve</h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          No path to the page you requested. Check the address, or head back to your dashboard.
        </p>
        {/* A link, styled as a button — nesting an <a> inside a <button> would
            be invalid HTML and breaks keyboard and middle-click behaviour. */}
        <Link
          to="/dashboard"
          className="mt-7 inline-flex h-12 items-center justify-center rounded-[var(--radius-md)] bg-accent-500 px-6 text-base font-medium text-white transition-colors duration-[var(--duration-fast)] hover:bg-accent-600 active:scale-[0.97]"
        >
          Return to dashboard
        </Link>
      </GlassPanel>
    </div>
  );
}
