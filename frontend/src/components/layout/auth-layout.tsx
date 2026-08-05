import { motion } from 'motion/react';
import type { ReactNode } from 'react';

import { Wordmark } from '@/components/ui/logo';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { GlassPanel } from '@/components/ui/glass-panel';

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Centred glass card over the ambient gradient — the sign-in surface. */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-6 py-5 sm:px-10">
        <Wordmark />
        <ThemeToggle />
      </header>

      <main className="flex flex-1 items-center justify-center px-5 pb-16">
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-[27rem]"
        >
          <GlassPanel material="strong" radius="2xl" className="p-8 sm:p-10">
            <div className="mb-7 flex flex-col gap-2">
              <h1 className="text-display text-[26px] leading-tight font-semibold">{title}</h1>
              <p className="text-sm text-[var(--text-secondary)]">{subtitle}</p>
            </div>

            {children}

            {footer && (
              <div className="hairline-t mt-7 pt-5 text-center text-sm text-[var(--text-secondary)]">
                {footer}
              </div>
            )}
          </GlassPanel>
        </motion.div>
      </main>
    </div>
  );
}
