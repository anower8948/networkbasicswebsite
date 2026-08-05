/**
 * The device configuration window, opened by double-clicking a device.
 *
 * Tabs across the top: forms for what the device supports, a live CLI, and
 * read-only `show` output. All three read one `DeviceConfig`, so a change made
 * on any tab is visible on the others the moment you switch.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { Terminal, TriangleAlert, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { CliTerminal } from './cli-terminal';
import {
  GeneralForm,
  InterfaceForm,
  RoutingForm,
  VlanForm,
  type ConfigPatch,
} from './config-forms';
import { DeviceIcon } from './device-icon';
import { deviceColor } from './device-colors';
import { deviceApi } from '../api/device-api';
import { cn } from '@/lib/cn';
import { ApiError } from '@/lib/api-client';
import type { DeviceConfig } from '@/types/device-config';
import type { DeviceSpec, TopologyDevice, TopologyDocument } from '@/types/topology';

type TabId = 'general' | 'interfaces' | 'vlans' | 'routing' | 'cli' | 'show';

interface DeviceConfigWindowProps {
  document: TopologyDocument;
  device: TopologyDevice;
  spec: DeviceSpec;
  onChange: (config: DeviceConfig) => void;
  onClose: () => void;
}

/** Which tabs a device actually supports. */
function tabsFor(spec: DeviceSpec): { id: TabId; label: string }[] {
  const tabs: { id: TabId; label: string }[] = [
    { id: 'general', label: 'General' },
    { id: 'interfaces', label: 'Interfaces' },
  ];

  // A VLAN database belongs to switches, not to PCs.
  if (spec.kind === 'switch' || spec.kind === 'multilayer_switch') {
    tabs.push({ id: 'vlans', label: 'VLANs' });
  }
  // Routing is for devices that forward between networks.
  if (['router', 'multilayer_switch', 'firewall', 'isp'].includes(spec.kind)) {
    tabs.push({ id: 'routing', label: 'Routing' });
  }
  if (spec.hasCli) {
    tabs.push({ id: 'cli', label: 'CLI' });
  }
  tabs.push({ id: 'show', label: 'Show' });
  return tabs;
}

export function DeviceConfigWindow({
  document: topology,
  device,
  spec,
  onChange,
  onClose,
}: DeviceConfigWindowProps) {
  const tabs = tabsFor(spec);
  const [tab, setTab] = useState<TabId>('general');
  // `TopologyDevice.config` is deliberately untyped in the topology schema —
  // the designer round-trips it without knowing its shape. This is where it
  // gains a type.
  const [config, setConfig] = useState<DeviceConfig>(device.config ?? {});
  const [warnings, setWarnings] = useState<string[]>([]);

  // Validate on the server as the configuration changes. Debounced, because a
  // request per keystroke would be wasteful and would flash errors at someone
  // halfway through typing an address.
  const validate = useMutation({
    mutationFn: (next: DeviceConfig) =>
      deviceApi.saveConfig(topology, device.id, next),
    onSuccess: (result) => setWarnings(result.warnings),
  });

  useEffect(() => {
    const timer = setTimeout(() => validate.mutate(config), 400);
    return () => clearTimeout(timer);
    // `validate` is a stable mutation object; re-running on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const views = useQuery({
    queryKey: ['device-views', device.id, JSON.stringify(config)],
    queryFn: () => deviceApi.views(topology, device.id, config),
    enabled: tab === 'show',
  });

  const applyPatch = (patch: ConfigPatch) => {
    // Derived outside the updater on purpose: React may run a functional
    // updater during render, and `onChange` writes to the simulator page, so
    // calling it in there sets state on another component mid-render. Patches
    // only ever come from event handlers, where `config` is already current.
    const next = patch(config);
    setConfig(next);
    onChange(next);
  };

  // Escape closes, as a window should.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const formProps = { config, spec, onChange: applyPatch };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close configuration"
        onClick={onClose}
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
      />

      <GlassPanel
        material="strong"
        radius="2xl"
        className="relative flex h-[min(80dvh,760px)] w-full max-w-4xl flex-col overflow-hidden"
      >
        <header className="hairline-b flex items-center gap-3 px-5 py-3.5">
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: `color-mix(in oklab, ${deviceColor(device.kind)} 16%, transparent)`,
            }}
          >
            <DeviceIcon kind={device.kind} className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-title text-[15px] font-semibold">
              {config.hostname || device.name}
            </h2>
            <p className="truncate text-[12px] text-[var(--text-tertiary)]">
              {spec.label} · {spec.model}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-[var(--radius-xs)] p-1.5 text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]"
          >
            <X className="size-5" />
          </button>
        </header>

        <div
          role="tablist"
          aria-label="Configuration sections"
          className="hairline-b flex gap-0.5 px-3 py-2"
        >
          {tabs.map((item) => (
            <button
              key={item.id}
              role="tab"
              type="button"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] font-medium',
                'transition-all duration-[var(--duration-fast)]',
                tab === item.id
                  ? 'bg-[var(--surface-raised)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
              )}
            >
              {item.id === 'cli' && <Terminal className="size-3.5" aria-hidden />}
              {item.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {validate.error instanceof ApiError && (
            <Alert tone="danger" className="mb-4">
              {validate.error.status === 422
                ? 'That configuration is not valid — check the addresses and masks.'
                : validate.error.message}
            </Alert>
          )}

          {warnings.length > 0 && tab !== 'cli' && (
            <div className="mb-4 flex flex-col gap-2">
              {warnings.map((warning) => (
                <Alert key={warning} tone="warning">
                  <span className="flex items-start gap-2">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    {warning}
                  </span>
                </Alert>
              ))}
            </div>
          )}

          {tab === 'general' && <GeneralForm {...formProps} />}
          {tab === 'interfaces' && <InterfaceForm {...formProps} />}
          {tab === 'vlans' && <VlanForm {...formProps} />}
          {tab === 'routing' && <RoutingForm {...formProps} />}

          {tab === 'cli' && (
            <div className="h-[min(52dvh,460px)]">
              <CliTerminal
                document={topology}
                deviceId={device.id}
                deviceName={device.name}
                config={config}
                onConfigChange={(next) => {
                  setConfig(next);
                  onChange(next);
                }}
              />
            </div>
          )}

          {tab === 'show' && (
            <div className="flex flex-col gap-5">
              {views.isLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner label="Rendering output" />
                </div>
              ) : views.data ? (
                <>
                  <ShowBlock title="show running-config" body={views.data.runningConfig} />
                  <ShowBlock
                    title="show ip interface brief"
                    body={views.data.interfaceBrief}
                  />
                  <ShowBlock title="show ip route" body={views.data.ipRoute} />
                </>
              ) : (
                <Alert tone="danger">Could not render the device output.</Alert>
              )}
            </div>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}

function ShowBlock({ title, body }: { title: string; body: string }) {
  return (
    <section>
      <h3 className="mb-2 font-mono text-[12px] font-semibold text-[var(--text-secondary)]">
        {title}
      </h3>
      <pre className="overflow-x-auto rounded-[var(--radius-sm)] bg-[oklch(0.16_0.012_265)] p-3 font-mono text-[12px] leading-[1.55] text-[oklch(0.82_0.01_250)]">
        {body}
      </pre>
    </section>
  );
}
