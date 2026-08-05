/**
 * A live IPv4 subnet calculator.
 *
 * Genuinely useful rather than decorative: it shows the magic-number working
 * the subnetting lesson teaches, so a learner can check their hand calculation
 * against it and see *why* the answer is what it is.
 *
 * All arithmetic is done here with unsigned 32-bit integers. `>>> 0` appears
 * throughout because JavaScript's bitwise operators produce **signed** 32-bit
 * results — without it, any address with the high bit set (128.x.x.x and up)
 * comes out negative.
 */

import { useMemo, useState } from 'react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';

interface SubnetFacts {
  networkAddress: string;
  broadcastAddress: string;
  firstHost: string;
  lastHost: string;
  usableHosts: number;
  totalAddresses: number;
  mask: string;
  wildcard: string;
  magicNumber: number;
  interestingOctet: number;
  binaryAddress: string;
  binaryMask: string;
}

function parseIPv4(value: string): number | null {
  const parts = value.trim().split('.');
  if (parts.length !== 4) return null;

  let result = 0;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    result = (result << 8) | octet;
  }
  return result >>> 0;
}

function toDotted(value: number): string {
  return [24, 16, 8, 0].map((shift) => ((value >>> shift) & 255).toString()).join('.');
}

function toBinary(value: number): string {
  return [24, 16, 8, 0]
    .map((shift) => ((value >>> shift) & 255).toString(2).padStart(8, '0'))
    .join('.');
}

function calculate(address: string, prefix: number): SubnetFacts | null {
  const ip = parseIPv4(address);
  if (ip === null || prefix < 0 || prefix > 32) return null;

  // A /0 mask would shift by 32, which is undefined in JS (it shifts by 0).
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  const network = (ip & mask) >>> 0;
  const broadcast = (network | (~mask >>> 0)) >>> 0;
  const totalAddresses = 2 ** (32 - prefix);

  // /31 (RFC 3021 point-to-point) and /32 (host route) have no network and
  // broadcast addresses to subtract.
  const usableHosts = prefix >= 31 ? (prefix === 32 ? 1 : 2) : Math.max(totalAddresses - 2, 0);

  const interestingOctet = Math.min(Math.floor(prefix / 8), 3);
  const maskOctet = (mask >>> (24 - interestingOctet * 8)) & 255;

  return {
    networkAddress: toDotted(network),
    broadcastAddress: toDotted(broadcast),
    firstHost: toDotted(prefix >= 31 ? network : (network + 1) >>> 0),
    lastHost: toDotted(prefix >= 31 ? broadcast : (broadcast - 1) >>> 0),
    usableHosts,
    totalAddresses,
    mask: toDotted(mask),
    wildcard: toDotted(~mask >>> 0),
    magicNumber: 256 - maskOctet,
    interestingOctet,
    binaryAddress: toBinary(ip),
    binaryMask: toBinary(mask),
  };
}

/** Colours the network portion of a binary string differently from the host. */
function BinaryView({ binary, prefix }: { binary: string; prefix: number }) {
  const bits = binary.replace(/\./g, '');
  const groups = [0, 1, 2, 3].map((index) => bits.slice(index * 8, index * 8 + 8));

  let seen = 0;
  return (
    <span className="font-mono text-[12px] break-all">
      {groups.map((group, groupIndex) => {
        const rendered = (
          <span key={groupIndex}>
            {group.split('').map((bit, bitIndex) => {
              const position = seen + bitIndex;
              return (
                <span
                  key={bitIndex}
                  className={
                    position < prefix
                      ? 'text-accent-600 dark:text-accent-400'
                      : 'text-[var(--text-tertiary)]'
                  }
                >
                  {bit}
                </span>
              );
            })}
            {groupIndex < 3 && <span className="text-[var(--text-tertiary)]">.</span>}
          </span>
        );
        seen += 8;
        return rendered;
      })}
    </span>
  );
}

function Fact({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-[13px] text-[var(--text-secondary)]">{label}</dt>
      <dd className={cn('text-[13px] font-medium', mono && 'font-mono')}>{value}</dd>
    </div>
  );
}

export function SubnetCalculator() {
  const [address, setAddress] = useState('192.168.1.100');
  const [prefix, setPrefix] = useState(26);

  const facts = useMemo(() => calculate(address, prefix), [address, prefix]);
  const isValid = facts !== null;

  return (
    <GlassPanel radius="lg" className="p-5">
      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <Input
          label="IPv4 address"
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          spellCheck={false}
          className="font-mono"
          error={!isValid && address.trim() ? 'Enter a valid IPv4 address.' : undefined}
        />
        <div className="flex w-full flex-col gap-1.5 sm:w-32">
          <label
            htmlFor="subnet-prefix"
            className="text-[13px] font-medium text-[var(--text-secondary)]"
          >
            Prefix
          </label>
          <select
            id="subnet-prefix"
            value={prefix}
            onChange={(event) => setPrefix(Number(event.target.value))}
            className="glass-inset h-11 rounded-[var(--radius-sm)] px-3 font-mono text-sm focus:border-accent-500 focus:outline-none"
          >
            {Array.from({ length: 25 }, (_, index) => index + 8).map((value) => (
              <option key={value} value={value}>
                /{value}
              </option>
            ))}
          </select>
        </div>
      </div>

      {facts && (
        <>
          <div className="mt-5 grid gap-x-8 gap-y-0 sm:grid-cols-2">
            <dl className="divide-y divide-[var(--hairline)]">
              <Fact label="Network address" value={facts.networkAddress} />
              <Fact label="Broadcast address" value={facts.broadcastAddress} />
              <Fact label="First usable host" value={facts.firstHost} />
              <Fact label="Last usable host" value={facts.lastHost} />
            </dl>
            <dl className="divide-y divide-[var(--hairline)]">
              <Fact label="Subnet mask" value={facts.mask} />
              <Fact label="Wildcard mask" value={facts.wildcard} />
              <Fact label="Usable hosts" value={facts.usableHosts.toLocaleString()} />
              <Fact label="Total addresses" value={facts.totalAddresses.toLocaleString()} />
            </dl>
          </div>

          <div className="hairline-t mt-4 pt-4">
            <p className="text-[12px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
              Binary
            </p>
            <div className="mt-2 flex flex-col gap-1.5">
              <div className="flex items-baseline gap-3">
                <span className="w-16 shrink-0 text-[12px] text-[var(--text-tertiary)]">
                  Address
                </span>
                <BinaryView binary={facts.binaryAddress} prefix={prefix} />
              </div>
              <div className="flex items-baseline gap-3">
                <span className="w-16 shrink-0 text-[12px] text-[var(--text-tertiary)]">Mask</span>
                <BinaryView binary={facts.binaryMask} prefix={prefix} />
              </div>
            </div>
            <p className="mt-2.5 text-[12px] text-[var(--text-tertiary)]">
              <span className="text-accent-600 dark:text-accent-400">Blue</span> bits are the
              network portion; grey bits are the host portion.
            </p>
          </div>

          {prefix % 8 !== 0 && (
            <div className="hairline-t mt-4 pt-4">
              <p className="text-[12px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
                Magic number
              </p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
                The interesting octet is number {facts.interestingOctet + 1}, so the magic
                number is <strong className="font-mono">{facts.magicNumber}</strong>. Subnets
                start at multiples of {facts.magicNumber} in that octet.
              </p>
            </div>
          )}
        </>
      )}
    </GlassPanel>
  );
}
