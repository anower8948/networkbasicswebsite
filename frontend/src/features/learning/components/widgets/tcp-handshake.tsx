/** An animated TCP three-way handshake. */

import { motion } from 'motion/react';
import { Play, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cn } from '@/lib/cn';

interface Step {
  label: string;
  direction: 'to-server' | 'to-client';
  detail: string;
}

const STEPS: Step[] = [
  {
    label: 'SYN',
    direction: 'to-server',
    detail: 'The client proposes a connection and sends its initial sequence number.',
  },
  {
    label: 'SYN-ACK',
    direction: 'to-client',
    detail: "The server acknowledges the client's sequence number and sends its own.",
  },
  {
    label: 'ACK',
    direction: 'to-server',
    detail: "The client acknowledges the server's number. The connection is established.",
  },
];

const STEP_MS = 1400;

export function TCPHandshake() {
  const [step, setStep] = useState(-1);
  const isRunning = step >= 0 && step < STEPS.length;

  useEffect(() => {
    if (!isRunning) return;
    const timer = setTimeout(() => setStep((value) => value + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [step, isRunning]);

  const isComplete = step >= STEPS.length;

  return (
    <GlassPanel radius="lg" className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[13px] font-medium">
          <span className="rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] px-2.5 py-1">
            Client
          </span>
          <span className="text-[var(--text-tertiary)]">⟷</span>
          <span className="rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] px-2.5 py-1">
            Server
          </span>
        </div>
        <Button
          size="sm"
          variant="secondary"
          leadingIcon={
            isComplete ? <RotateCcw className="size-3.5" /> : <Play className="size-3.5" />
          }
          onClick={() => setStep(0)}
          disabled={isRunning}
        >
          {isComplete ? 'Replay' : 'Play'}
        </Button>
      </div>

      <div className="mt-5 flex flex-col gap-3">
        {STEPS.map((item, index) => {
          const hasFired = step >= index;

          return (
            <div key={item.label} className="flex flex-col gap-1.5">
              <div className="relative h-9 overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]">
                {hasFired && (
                  <motion.span
                    // Travels in the direction the message actually flows.
                    initial={{
                      left: item.direction === 'to-server' ? '2%' : '78%',
                      opacity: 0,
                    }}
                    animate={{
                      left: item.direction === 'to-server' ? '78%' : '2%',
                      opacity: 1,
                    }}
                    transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
                    className={cn(
                      'absolute top-1/2 -translate-y-1/2 rounded-[var(--radius-xs)] px-2.5 py-1',
                      'font-mono text-[12px] font-semibold text-white',
                      item.direction === 'to-server' ? 'bg-accent-500' : 'bg-[var(--color-success)]',
                    )}
                  >
                    {item.label}
                  </motion.span>
                )}
              </div>
              <p
                className={cn(
                  'text-[13px] transition-opacity duration-300',
                  hasFired ? 'text-[var(--text-secondary)]' : 'text-[var(--text-tertiary)] opacity-50',
                )}
              >
                <span className="font-medium">{item.label}</span> — {item.detail}
              </p>
            </div>
          );
        })}
      </div>

      {isComplete && (
        <p className="mt-4 rounded-[var(--radius-sm)] bg-[var(--color-success)]/10 px-3.5 py-2.5 text-[13px] text-[var(--color-success)]">
          Connection established — data can now flow in both directions.
        </p>
      )}
    </GlassPanel>
  );
}
