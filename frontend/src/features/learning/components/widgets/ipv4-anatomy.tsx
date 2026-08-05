/** Breaks an IPv4 address into its octets, showing decimal and binary. */

import { useState } from 'react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { Input } from '@/components/ui/input';

function octetsOf(value: string): number[] | null {
  const parts = value.trim().split('.');
  if (parts.length !== 4) return null;

  const octets: number[] = [];
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    octets.push(octet);
  }
  return octets;
}

/** The place value of each bit in an octet — 128 down to 1. */
const BIT_VALUES = [128, 64, 32, 16, 8, 4, 2, 1];

export function IPv4Anatomy() {
  const [address, setAddress] = useState('192.168.1.10');
  const octets = octetsOf(address);

  return (
    <GlassPanel radius="lg" className="p-5">
      <Input
        label="IPv4 address"
        value={address}
        onChange={(event) => setAddress(event.target.value)}
        spellCheck={false}
        className="font-mono"
        error={!octets && address.trim() ? 'Enter four octets, each 0–255.' : undefined}
      />

      {octets && (
        <>
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {octets.map((octet, index) => (
              <div
                key={index}
                className="rounded-[var(--radius-sm)] border border-[var(--hairline)] p-3"
              >
                <p className="text-[11px] tracking-wide text-[var(--text-tertiary)] uppercase">
                  Octet {index + 1}
                </p>
                <p className="text-title mt-1 font-mono text-xl font-semibold">{octet}</p>
                <p className="mt-1 font-mono text-[12px] text-[var(--text-secondary)]">
                  {octet.toString(2).padStart(8, '0')}
                </p>
              </div>
            ))}
          </div>

          <div className="hairline-t mt-4 pt-4">
            <p className="text-[12px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
              How octet 1 adds up
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {BIT_VALUES.map((value) => {
                const isSet = ((octets[0] ?? 0) & value) !== 0;
                return (
                  <span
                    key={value}
                    className={
                      isSet
                        ? 'rounded-[var(--radius-xs)] bg-accent-500 px-2 py-1 font-mono text-[12px] text-white'
                        : 'rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] px-2 py-1 font-mono text-[12px] text-[var(--text-tertiary)]'
                    }
                  >
                    {value}
                  </span>
                );
              })}
            </div>
            <p className="mt-2 font-mono text-[13px] text-[var(--text-secondary)]">
              {BIT_VALUES.filter((value) => ((octets[0] ?? 0) & value) !== 0).join(' + ') || '0'}{' '}
              = {octets[0]}
            </p>
            <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">
              Every octet works the same way. All eight bits set gives 255 — which is why no
              octet can be larger.
            </p>
          </div>
        </>
      )}
    </GlassPanel>
  );
}
