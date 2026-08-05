/**
 * The foundational glass surface. Every card, sheet, popover and toolbar in the
 * application is a `GlassPanel` with a different material and radius, which is
 * what keeps the translucency consistent across the app.
 */

import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react';

import { cn } from '@/lib/cn';

export type GlassMaterial = 'regular' | 'strong' | 'thin';
export type GlassRadius = 'sm' | 'md' | 'lg' | 'xl' | '2xl';

const MATERIALS: Record<GlassMaterial, string> = {
  /** Default panel: medium blur, good for cards over a busy background. */
  regular: 'glass',
  /** Modals and sheets — heavier blur so content behind is fully de-emphasised. */
  strong: 'glass-strong',
  /** Sidebars and toolbars where content scrolls underneath. */
  thin: 'glass-thin',
};

const RADII: Record<GlassRadius, string> = {
  sm: 'rounded-[var(--radius-sm)]',
  md: 'rounded-[var(--radius-md)]',
  lg: 'rounded-[var(--radius-lg)]',
  xl: 'rounded-[var(--radius-xl)]',
  '2xl': 'rounded-[var(--radius-2xl)]',
};

interface GlassPanelProps extends ComponentPropsWithoutRef<'div'> {
  material?: GlassMaterial;
  radius?: GlassRadius;
  /** Adds the hover-lift and press-scale interaction. */
  interactive?: boolean;
  as?: ElementType;
  children?: ReactNode;
}

export function GlassPanel({
  material = 'regular',
  radius = 'lg',
  interactive = false,
  as: Component = 'div',
  className,
  children,
  ...props
}: GlassPanelProps) {
  return (
    <Component
      className={cn(
        MATERIALS[material],
        RADII[radius],
        interactive && 'glass-interactive',
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  );
}
