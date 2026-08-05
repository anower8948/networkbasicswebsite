import { AlertCircle, CheckCircle2, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<AlertTone, { color: string; Icon: typeof Info }> = {
  info: { color: 'var(--color-info)', Icon: Info },
  success: { color: 'var(--color-success)', Icon: CheckCircle2 },
  warning: { color: 'var(--color-warning)', Icon: TriangleAlert },
  danger: { color: 'var(--color-danger)', Icon: AlertCircle },
};

interface AlertProps {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * An inline status message.
 *
 * Errors and warnings use `role="alert"` so they are announced immediately;
 * info and success use `role="status"`, which is polite and does not interrupt
 * whatever the screen reader is currently saying.
 */
export function Alert({ tone = 'info', title, children, action, className }: AlertProps) {
  const { color, Icon } = TONES[tone];
  const isUrgent = tone === 'danger' || tone === 'warning';

  return (
    <div
      role={isUrgent ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-3 rounded-[var(--radius-md)] border p-4',
        className,
      )}
      style={{
        borderColor: `color-mix(in oklab, ${color} 30%, transparent)`,
        backgroundColor: `color-mix(in oklab, ${color} 10%, transparent)`,
      }}
    >
      <Icon className="mt-px size-[18px] shrink-0" style={{ color }} aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="text-sm font-medium">{title}</p>}
        {children && (
          <div className={cn('text-[13px] text-[var(--text-secondary)]', title && 'mt-1')}>
            {children}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
