/** An interactive OSI layer explorer. Click a layer to see its detail. */

import { motion } from 'motion/react';
import { useState } from 'react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { cn } from '@/lib/cn';

interface Layer {
  number: number;
  name: string;
  pdu: string;
  responsibility: string;
  examples: string;
  troubleshooting: string;
  hue: number;
}

// Ordered top-down, matching how the stack is conventionally drawn.
const LAYERS: Layer[] = [
  {
    number: 7,
    name: 'Application',
    pdu: 'Data',
    responsibility: 'Provides network services directly to the user’s application.',
    examples: 'HTTP, DNS, SMTP, FTP, DHCP',
    troubleshooting: 'Can the application resolve names and reach the service?',
    hue: 300,
  },
  {
    number: 6,
    name: 'Presentation',
    pdu: 'Data',
    responsibility: 'Translates, encrypts and compresses data into a common format.',
    examples: 'TLS, JPEG, ASCII, MPEG',
    troubleshooting: 'Is the certificate valid? Is the encoding what the peer expects?',
    hue: 285,
  },
  {
    number: 5,
    name: 'Session',
    pdu: 'Data',
    responsibility: 'Opens, manages and closes conversations between applications.',
    examples: 'RPC, NetBIOS, SQL sessions',
    troubleshooting: 'Are sessions being dropped or timing out early?',
    hue: 265,
  },
  {
    number: 4,
    name: 'Transport',
    pdu: 'Segment',
    responsibility: 'End-to-end delivery, port numbers, and reliability where required.',
    examples: 'TCP, UDP',
    troubleshooting: 'Is the port open? Is a firewall dropping the handshake?',
    hue: 245,
  },
  {
    number: 3,
    name: 'Network',
    pdu: 'Packet',
    responsibility: 'Logical addressing and choosing a path between networks.',
    examples: 'IP, ICMP, OSPF, EIGRP',
    troubleshooting: 'Can you ping the gateway? Is there a route to the destination?',
    hue: 225,
  },
  {
    number: 2,
    name: 'Data Link',
    pdu: 'Frame',
    responsibility: 'Delivery across a single link, using physical addresses.',
    examples: 'Ethernet, ARP, PPP, switching',
    troubleshooting: 'Is the MAC address in the table? Is the VLAN correct?',
    hue: 175,
  },
  {
    number: 1,
    name: 'Physical',
    pdu: 'Bits',
    responsibility: 'Transmits raw bits as electrical, optical or radio signals.',
    examples: 'Cables, connectors, radio, repeaters',
    troubleshooting: 'Is the interface up? Is the cable the right type and seated?',
    hue: 150,
  },
];

export function OSIStack() {
  const [selected, setSelected] = useState<number>(3);
  const active = LAYERS.find((layer) => layer.number === selected) ?? LAYERS[4]!;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div role="tablist" aria-label="OSI layers" className="flex flex-col gap-1.5">
        {LAYERS.map((layer) => {
          const isActive = layer.number === selected;
          const color = `oklch(0.66 0.16 ${layer.hue})`;

          return (
            <button
              key={layer.number}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls="osi-layer-detail"
              onClick={() => setSelected(layer.number)}
              className={cn(
                'flex items-center gap-3 rounded-[var(--radius-sm)] border px-3.5 py-2.5 text-left',
                'transition-all duration-[var(--duration-fast)]',
                isActive ? 'shadow-sm' : 'hover:translate-x-1',
              )}
              style={{
                borderColor: isActive
                  ? `color-mix(in oklab, ${color} 50%, transparent)`
                  : 'var(--hairline)',
                backgroundColor: isActive
                  ? `color-mix(in oklab, ${color} 12%, transparent)`
                  : 'transparent',
              }}
            >
              <span
                aria-hidden
                className="flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-xs)] text-[13px] font-semibold text-white"
                style={{ backgroundColor: color }}
              >
                {layer.number}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-medium">{layer.name}</span>
              </span>
              <span className="shrink-0 font-mono text-[11px] text-[var(--text-tertiary)]">
                {layer.pdu}
              </span>
            </button>
          );
        })}
      </div>

      <GlassPanel
        id="osi-layer-detail"
        role="tabpanel"
        radius="lg"
        className="h-fit p-5"
        material="thin"
      >
        <motion.div
          // Re-keying replays the transition, so switching layers reads as a
          // change rather than an instant swap.
          key={active.number}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          <p
            className="text-[12px] font-semibold tracking-wide uppercase"
            style={{ color: `oklch(0.6 0.16 ${active.hue})` }}
          >
            Layer {active.number}
          </p>
          <h4 className="text-title mt-1 text-lg font-semibold">{active.name}</h4>
          <p className="mt-2.5 text-[14px] leading-relaxed text-[var(--text-secondary)]">
            {active.responsibility}
          </p>

          <dl className="mt-4 flex flex-col gap-3">
            <div>
              <dt className="text-[12px] text-[var(--text-tertiary)]">Data unit</dt>
              <dd className="font-mono text-[14px]">{active.pdu}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-[var(--text-tertiary)]">Examples</dt>
              <dd className="text-[14px]">{active.examples}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-[var(--text-tertiary)]">Ask when troubleshooting</dt>
              <dd className="text-[14px] text-[var(--text-secondary)]">
                {active.troubleshooting}
              </dd>
            </div>
          </dl>
        </motion.div>
      </GlassPanel>
    </div>
  );
}
