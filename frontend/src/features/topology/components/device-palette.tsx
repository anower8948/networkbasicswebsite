/**
 * The device palette.
 *
 * Devices are added by dragging onto the canvas or by clicking, which drops
 * one in the middle of the current view. Click-to-add exists because
 * drag-and-drop is awkward on touch devices and impossible by keyboard.
 */

import { useState } from 'react';

import { DeviceIcon } from './device-icon';
import { deviceColor } from './device-colors';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';
import type { DeviceSpec } from '@/types/topology';

/** Grouped so the palette reads as a shelf of equipment, not an alphabet. */
const CATEGORIES: { title: string; kinds: string[] }[] = [
  { title: 'Endpoints', kinds: ['pc', 'laptop', 'server', 'nas', 'printer', 'ip_phone', 'camera', 'iot'] },
  { title: 'Network', kinds: ['switch', 'multilayer_switch', 'router', 'firewall'] },
  { title: 'Wireless', kinds: ['wireless_router', 'access_point'] },
  { title: 'External', kinds: ['cloud', 'isp'] },
];

interface DevicePaletteProps {
  catalog: DeviceSpec[];
  onAdd: (kind: DeviceSpec['kind']) => void;
}

export function DevicePalette({ catalog, onAdd }: DevicePaletteProps) {
  const [query, setQuery] = useState('');
  const byKind = new Map(catalog.map((spec) => [spec.kind, spec]));

  const matches = (spec: DeviceSpec) =>
    !query ||
    spec.label.toLowerCase().includes(query.toLowerCase()) ||
    spec.model.toLowerCase().includes(query.toLowerCase());

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search devices"
        aria-label="Search devices"
        className="h-9 text-[13px]"
      />

      {CATEGORIES.map((category) => {
        const specs = category.kinds
          .map((kind) => byKind.get(kind as DeviceSpec['kind']))
          .filter((spec): spec is DeviceSpec => Boolean(spec) && matches(spec as DeviceSpec));

        if (specs.length === 0) return null;

        return (
          <section key={category.title} className="flex flex-col gap-1.5">
            <h3 className="text-[11px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
              {category.title}
            </h3>
            <div className="grid grid-cols-2 gap-1.5">
              {specs.map((spec) => (
                <button
                  key={spec.kind}
                  type="button"
                  draggable
                  onDragStart={(event) => {
                    // Consumed by the canvas's onDrop handler.
                    event.dataTransfer.setData('application/nlp-device', spec.kind);
                    event.dataTransfer.effectAllowed = 'copy';
                  }}
                  onClick={() => onAdd(spec.kind)}
                  title={`${spec.model} — ${spec.description}`}
                  className={cn(
                    'flex cursor-grab flex-col items-center gap-1.5 rounded-[var(--radius-sm)] border p-2.5',
                    'border-[var(--hairline)] transition-all duration-[var(--duration-fast)]',
                    'hover:border-[var(--text-tertiary)] hover:bg-[var(--surface-sunken)] active:cursor-grabbing',
                  )}
                >
                  <span
                    className="flex size-8 items-center justify-center rounded-[var(--radius-xs)]"
                    style={{
                      backgroundColor: `color-mix(in oklab, ${deviceColor(spec.kind)} 16%, transparent)`,
                    }}
                  >
                    <DeviceIcon
                      kind={spec.kind}
                      className="size-4"
                    />
                  </span>
                  <span className="text-center text-[11px] leading-tight font-medium">
                    {spec.label}
                  </span>
                </button>
              ))}
            </div>
          </section>
        );
      })}

      <p className="mt-auto pt-2 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
        Drag a device onto the canvas, or click to drop one in view. Drag from the dot
        under a device to another to cable them. Double-click a device to configure it.
      </p>
    </div>
  );
}
