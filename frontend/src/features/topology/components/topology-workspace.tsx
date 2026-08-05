/**
 * Palette + canvas + side panel: the three-column workspace.
 *
 * Extracted from the simulator page when Part 8 needed the same surface inside
 * a lab. The two screens differ in their *chrome* — one has save and export,
 * the other has objectives and a submit button — but the editing surface itself
 * is identical, and two copies of it would have drifted within a part or two.
 *
 * All the state that belongs to the surface (what is selected, which device's
 * configuration window is open, the current simulation and its playback) lives
 * here. The host page owns only what it renders around the edges.
 */

import { useCallback, useState, type ReactNode } from 'react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { DeviceConfigWindow } from './device-config-window';
import { DevicePalette } from './device-palette';
import { Inspector } from './inspector';
import { SimulationPanel } from './simulation-panel';
import { TopologyCanvas } from './topology-canvas';
import { usePacketAnimation } from '../hooks/use-packet-animation';
import type { TopologyEditor } from '../hooks/use-topology-editor';
import { cn } from '@/lib/cn';
import type { SimulationResult } from '@/types/simulation';
import type { DeviceKind, DeviceSpec, LinkIssue } from '@/types/topology';

export interface WorkspaceTab {
  id: string;
  label: string;
  content: ReactNode;
}

interface TopologyWorkspaceProps {
  editor: TopologyEditor;
  catalog: DeviceSpec[];
  issues: LinkIssue[];
  onConnect: (source: string, target: string) => void;
  /** Panels shown before Inspect and Simulate — the lab briefing, for one. */
  leadingTabs?: WorkspaceTab[];
  /** Labs hide the palette when the topology is meant to be configured, not built. */
  showPalette?: boolean;
}

export function TopologyWorkspace({
  editor,
  catalog,
  issues,
  onConnect,
  leadingTabs = [],
  showPalette = true,
}: TopologyWorkspaceProps) {
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null);
  const [configuringId, setConfiguringId] = useState<string | null>(null);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [activeTab, setActiveTab] = useState<string>(leadingTabs[0]?.id ?? 'inspect');

  const animation = usePacketAnimation(simulation);

  // Translate the current trace step into something the canvas can draw.
  const activePacket = (() => {
    const event = animation.currentEvent;
    if (!event?.linkId) return null;
    const link = editor.document.links.find((item) => item.id === event.linkId);
    // The edge is drawn source→target; a packet sent by the target runs the
    // other way along the same path.
    const reversed = link ? link.target.deviceId === event.deviceId : false;
    return {
      linkId: event.linkId,
      label: event.frame?.protocol ?? event.kind.replace(/_/g, ' '),
      reversed,
      ok: event.ok,
    };
  })();

  const configuringDevice =
    editor.document.devices.find((device) => device.id === configuringId) ?? null;
  const configuringSpec = configuringDevice
    ? (catalog.find((spec) => spec.kind === configuringDevice.kind) ?? null)
    : null;

  const addDeviceInView = useCallback(
    (kind: DeviceKind) => {
      // Click-to-add drops near the current viewport centre.
      const { x, y, zoom } = editor.document.viewport;
      editor.addDevice(kind, {
        x: Math.round(-x / zoom + 220 + Math.random() * 80),
        y: Math.round(-y / zoom + 140 + Math.random() * 80),
      });
    },
    [editor],
  );

  const tabs: WorkspaceTab[] = [
    ...leadingTabs,
    {
      id: 'inspect',
      label: 'Inspect',
      content: (
        <Inspector
          editor={editor}
          catalog={catalog}
          selectedDeviceId={selectedDeviceId}
          selectedLinkId={selectedLinkId}
          issues={issues}
        />
      ),
    },
    {
      id: 'simulate',
      label: 'Simulate',
      content: (
        <SimulationPanel
          document={editor.document}
          selectedDeviceId={selectedDeviceId}
          result={simulation}
          animation={animation}
          onResult={setSimulation}
        />
      ),
    },
  ];

  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  return (
    <>
      <div
        className={cn(
          'grid min-h-0 flex-1 grid-cols-1 gap-3',
          showPalette
            ? 'lg:grid-cols-[210px_minmax(0,1fr)_300px]'
            : 'lg:grid-cols-[minmax(0,1fr)_320px]',
        )}
      >
        {showPalette && (
          <GlassPanel radius="lg" className="hidden min-h-0 overflow-hidden lg:block">
            <DevicePalette catalog={catalog} onAdd={addDeviceInView} />
          </GlassPanel>
        )}

        <GlassPanel radius="lg" className="min-h-0 overflow-hidden">
          <TopologyCanvas
            editor={editor}
            catalog={catalog}
            issues={issues}
            selectedDeviceId={selectedDeviceId}
            selectedLinkId={selectedLinkId}
            onSelectDevice={setSelectedDeviceId}
            onSelectLink={setSelectedLinkId}
            onConnect={onConnect}
            onOpenDevice={setConfiguringId}
            activePacket={activePacket}
          />
        </GlassPanel>

        <GlassPanel radius="lg" className="hidden min-h-0 flex-col overflow-hidden lg:flex">
          <div role="tablist" aria-label="Side panel" className="hairline-b flex gap-0.5 p-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={active?.id === tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex-1 rounded-[var(--radius-sm)] px-3 py-1.5 text-[12px] font-medium',
                  active?.id === tab.id
                    ? 'bg-[var(--surface-raised)] shadow-sm'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">{active?.content}</div>
        </GlassPanel>
      </div>

      {configuringDevice && configuringSpec && (
        <DeviceConfigWindow
          // Keyed on the device: the window holds the working `DeviceConfig` in
          // its own state, seeded once on mount. Without a key, switching from
          // one device to another in a single render would reuse the instance —
          // and the next edit would write the *previous* device's config over
          // this one, silently wiping its interfaces.
          key={configuringDevice.id}
          document={editor.document}
          device={configuringDevice}
          spec={configuringSpec}
          onChange={(config) =>
            editor.configureDevice(configuringDevice.id, config as Record<string, unknown>)
          }
          onClose={() => setConfiguringId(null)}
        />
      )}
    </>
  );
}
