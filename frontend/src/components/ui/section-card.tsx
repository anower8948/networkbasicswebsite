import type { ReactNode } from 'react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { cn } from '@/lib/cn';

interface SectionCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

/** A titled settings panel — the repeating unit of the account screens. */
export function SectionCard({
  title,
  description,
  children,
  footer,
  className,
}: SectionCardProps) {
  return (
    <GlassPanel radius="xl" className={cn('overflow-hidden', className)}>
      <div className="p-6">
        <h2 className="text-title text-base font-semibold">{title}</h2>
        {description && (
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{description}</p>
        )}
        <div className="mt-5">{children}</div>
      </div>
      {footer && (
        <div className="hairline-t bg-[var(--surface-sunken)]/40 px-6 py-4">{footer}</div>
      )}
    </GlassPanel>
  );
}
