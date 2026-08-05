/**
 * The simulation panel: choose a protocol, run it, read the trace.
 *
 * The trace is the point. Every step says what a device decided and why, so a
 * failed ping is a lesson rather than a dead end — the failure reason and hint
 * are shown prominently, and each step can be clicked to see the frame headers
 * at that hop.
 */

import { useMutation } from '@tanstack/react-query';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Play,
  Pause,
  RotateCcw,
  Zap,
} from 'lucide-react';
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { simulationApi } from '../api/simulation-api';
import type { PacketAnimation } from '../hooks/use-packet-animation';
import { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/cn';
import {
  PROTOCOLS_WITHOUT_DESTINATION,
  PROTOCOL_LABELS,
  type SimulationProtocol,
  type SimulationResult,
  type TraceEvent,
} from '@/types/simulation';
import type { TopologyDocument } from '@/types/topology';

interface SimulationPanelProps {
  document: TopologyDocument;
  selectedDeviceId: string | null;
  result: SimulationResult | null;
  animation: PacketAnimation;
  onResult: (result: SimulationResult | null) => void;
}

/** Colour by what the step means, so the trace scans at a glance. */
function eventTone(event: TraceEvent): string {
  if (!event.ok) return 'var(--color-danger)';
  if (event.kind.startsWith('arp')) return 'var(--color-track-intermediate)';
  if (event.kind.startsWith('dhcp')) return 'var(--color-warning)';
  if (event.kind.startsWith('dns')) return 'var(--color-track-advanced)';
  if (event.kind.startsWith('tcp') || event.kind === 'udp_datagram') {
    return 'var(--color-info)';
  }
  if (event.kind === 'deliver' || event.kind === 'reply') return 'var(--color-success)';
  return 'var(--text-tertiary)';
}

function FrameHeaders({ frame }: { frame: NonNullable<TraceEvent['frame']> }) {
  const rows: [string, string | number | null][] = [
    ['Source MAC', frame.sourceMac],
    ['Dest MAC', frame.destinationMac],
    ['Source IP', frame.sourceIp],
    ['Dest IP', frame.destinationIp],
    ['Protocol', frame.protocol],
    ['TTL', frame.ttl],
    ['VLAN', frame.vlan],
  ];

  return (
    <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] p-2 font-mono text-[11px]">
      {rows.map(([label, value]) =>
        value === null || value === undefined ? null : (
          <div key={label} className="contents">
            <dt className="text-[var(--text-tertiary)]">{label}</dt>
            <dd className="truncate">{value}</dd>
          </div>
        ),
      )}
    </dl>
  );
}

export function SimulationPanel({
  document,
  selectedDeviceId,
  result,
  animation,
  onResult,
}: SimulationPanelProps) {
  const [protocol, setProtocol] = useState<SimulationProtocol>('ping');
  const [destination, setDestination] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);

  const source = document.devices.find((device) => device.id === selectedDeviceId);
  const needsDestination = !PROTOCOLS_WITHOUT_DESTINATION.includes(protocol);

  const run = useMutation({
    mutationFn: () =>
      simulationApi.run({
        document,
        sourceDeviceId: selectedDeviceId as string,
        protocol,
        destination: destination.trim(),
        port: protocol === 'tcp' ? 80 : 53,
      }),
    onSuccess: onResult,
  });

  const canRun = Boolean(selectedDeviceId) && (!needsDestination || destination.trim());

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div>
        <h3 className="text-title flex items-center gap-2 text-[13px] font-semibold">
          <Zap className="size-3.5 text-accent-500" aria-hidden />
          Simulate traffic
        </h3>
        <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
          {source
            ? `Sending from ${source.name}.`
            : 'Select a device on the canvas to send from.'}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="sim-protocol"
          className="text-[12px] font-medium text-[var(--text-secondary)]"
        >
          Protocol
        </label>
        <select
          id="sim-protocol"
          value={protocol}
          onChange={(event) => setProtocol(event.target.value as SimulationProtocol)}
          className="glass-inset h-9 rounded-[var(--radius-sm)] px-2.5 text-[13px] focus:border-accent-500 focus:outline-none"
        >
          {Object.entries(PROTOCOL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {needsDestination && (
        <Input
          label="Destination"
          value={destination}
          placeholder="10.0.0.10 or PC2"
          onChange={(event) => setDestination(event.target.value)}
          className="h-9 font-mono text-[13px]"
          hint="An IP address or a device name."
        />
      )}

      <Button
        size="sm"
        fullWidth
        isLoading={run.isPending}
        disabled={!canRun}
        onClick={() => run.mutate()}
      >
        Run simulation
      </Button>

      {run.error instanceof ApiError && (
        <Alert tone="danger">{run.error.message}</Alert>
      )}

      {result && (
        <>
          <Alert tone={result.success ? 'success' : 'danger'}>
            <span className="flex items-start gap-2">
              {result.success ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              ) : (
                <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              )}
              <span>
                <span className="block font-medium">{result.summary}</span>
                {result.failureReason && (
                  <span className="mt-1 block">{result.failureReason}</span>
                )}
                {result.hint && (
                  <span className="mt-1.5 block text-[var(--text-secondary)] italic">
                    {result.hint}
                  </span>
                )}
              </span>
            </span>
          </Alert>

          {/* Playback controls — stepping is what makes the trace teachable. */}
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={animation.stepBack}
              aria-label="Previous step"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={animation.isPlaying ? animation.pause : animation.play}
              leadingIcon={
                animation.isPlaying ? (
                  <Pause className="size-3.5" />
                ) : (
                  <Play className="size-3.5" />
                )
              }
            >
              {animation.isPlaying ? 'Pause' : 'Play'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={animation.stepForward}
              aria-label="Next step"
            >
              <ChevronRight className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={animation.reset}
              aria-label="Restart"
              className="ml-auto"
            >
              <RotateCcw className="size-3.5" />
            </Button>
          </div>

          <ol className="flex flex-col gap-1" aria-label="Simulation trace">
            {result.events.map((event, index) => {
              const isCurrent = index === animation.currentStep;
              const tone = eventTone(event);

              return (
                <li key={event.step}>
                  <button
                    type="button"
                    onClick={() => {
                      animation.seek(index);
                      setExpanded(expanded === index ? null : index);
                    }}
                    className={cn(
                      'w-full rounded-[var(--radius-xs)] border px-2.5 py-1.5 text-left',
                      'transition-all duration-[var(--duration-fast)]',
                      isCurrent
                        ? 'border-accent-500 bg-accent-500/10'
                        : 'border-transparent hover:bg-[var(--surface-sunken)]',
                    )}
                  >
                    <span className="flex items-baseline gap-2">
                      <span
                        aria-hidden
                        className="mt-1 size-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: tone }}
                      />
                      <span className="w-5 shrink-0 text-[10px] text-[var(--text-tertiary)] tabular-nums">
                        {event.step}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[11px] font-medium text-[var(--text-tertiary)]">
                          {event.deviceName}
                          {event.interface && ` · ${event.interface}`}
                        </span>
                        <span
                          className={cn(
                            'block text-[12px] leading-snug',
                            !event.ok && 'text-[var(--color-danger)]',
                          )}
                        >
                          {event.summary}
                        </span>
                      </span>
                    </span>

                    {(expanded === index || isCurrent) && event.detail && (
                      <span className="mt-1.5 block pl-9 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                        {event.detail}
                      </span>
                    )}
                    {expanded === index && event.frame && (
                      <span className="block pl-9">
                        <FrameHeaders frame={event.frame} />
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}
