import { AlertCircle } from 'lucide-react';
import { forwardRef, useId, type ComponentPropsWithoutRef, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface InputProps extends ComponentPropsWithoutRef<'input'> {
  label?: string;
  error?: string | undefined;
  hint?: string | undefined;
  leadingIcon?: ReactNode;
  trailingSlot?: ReactNode;
}

/**
 * A labelled text field on the inset glass material.
 *
 * `forwardRef` is required for react-hook-form's `register()` to attach to the
 * DOM node. Errors are wired with `aria-describedby` + `aria-invalid` so screen
 * readers announce them, and `role="alert"` makes the message live.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, leadingIcon, trailingSlot, className, id, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  const describedBy = [error ? errorId : null, hint && !error ? hintId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="flex w-full flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-[13px] font-medium text-[var(--text-secondary)]"
        >
          {label}
        </label>
      )}

      <div className="relative">
        {leadingIcon && (
          <span
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
            aria-hidden
          >
            {leadingIcon}
          </span>
        )}

        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={cn(
            'glass-inset h-11 w-full rounded-[var(--radius-sm)] text-sm',
            'text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]',
            'transition-[box-shadow,border-color] duration-[var(--duration-fast)]',
            'focus:outline-none focus:border-accent-500',
            'focus:shadow-[0_0_0_3px_oklch(0.62_0.19_255/0.18)]',
            leadingIcon ? 'pl-10' : 'pl-3.5',
            trailingSlot ? 'pr-11' : 'pr-3.5',
            error && 'border-[var(--color-danger)] focus:border-[var(--color-danger)]',
            className,
          )}
          {...props}
        />

        {trailingSlot && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2">{trailingSlot}</span>
        )}
      </div>

      {error ? (
        <p
          id={errorId}
          role="alert"
          className="flex items-center gap-1.5 text-[13px] text-[var(--color-danger)]"
        >
          <AlertCircle className="size-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      ) : (
        hint && (
          <p id={hintId} className="text-[13px] text-[var(--text-tertiary)]">
            {hint}
          </p>
        )
      )}
    </div>
  );
});
