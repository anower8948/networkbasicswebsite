/**
 * A device on the canvas.
 *
 * Connection handles are deliberately **per device, not per interface**: a
 * Catalyst 2960 has 26 usable ports, and rendering 26 targets would make the
 * node unusable and force a learner to choose a port number before they know
 * what one is. The server assigns the lowest free compatible port when the link
 * is made, and it stays editable in the inspector afterwards.
 */

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { memo } from 'react';

import { DeviceIcon } from './device-icon';
import { deviceColor } from './device-colors';
import { cn } from '@/lib/cn';
import type { DeviceKind } from '@/types/topology';

export interface DeviceNodeData extends Record<string, unknown> {
  kind: DeviceKind;
  name: string;
  label: string | null;
  /** Interfaces in use, shown as a port count badge. */
  linkCount: number;
  totalPorts: number;
  hasWarning: boolean;
}

function DeviceNodeComponent({ data, selected }: NodeProps) {
  const node = data as DeviceNodeData;
  const color = deviceColor(node.kind);

  // One handle of each type, stacked at the same point so a drag from anywhere
  // on the node starts a connection and any node can receive it.
  const handleStyle = {
    width: 10,
    height: 10,
    background: color,
    border: '2px solid var(--surface-raised)',
  } as const;

  return (
    <div
      className={cn(
        'group relative flex w-[104px] flex-col items-center gap-1.5 rounded-[var(--radius-md)] px-2 py-2.5',
        'border transition-shadow duration-[var(--duration-fast)]',
        selected
          ? 'border-accent-500 shadow-[0_0_0_3px_oklch(0.62_0.19_255/0.22)]'
          : 'border-[var(--hairline)] hover:border-[var(--text-tertiary)]',
      )}
      style={{ backgroundColor: 'var(--surface-raised)' }}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} />

      <span
        className="flex size-11 items-center justify-center rounded-[var(--radius-sm)]"
        style={{ backgroundColor: `color-mix(in oklab, ${color} 16%, transparent)` }}
      >
        <DeviceIcon kind={node.kind} className="size-6" />
      </span>

      <span className="max-w-full truncate text-[12px] font-semibold" title={node.name}>
        {node.name}
      </span>

      {node.label && (
        <span
          className="max-w-full truncate text-[10px] text-[var(--text-tertiary)]"
          title={node.label}
        >
          {node.label}
        </span>
      )}

      <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums">
        {node.linkCount}/{node.totalPorts} ports
      </span>

      {node.hasWarning && (
        <span
          role="img"
          aria-label="This device has a cabling warning"
          title="Cabling warning"
          className="absolute -top-1.5 -right-1.5 flex size-4 items-center justify-center rounded-full bg-[var(--color-warning)] text-[10px] font-bold text-white"
        >
          !
        </span>
      )}

      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
}

// Memoised: React Flow re-renders every node on any canvas change, and a
// 200-device topology would otherwise redraw all of them on each drag frame.
export const DeviceNode = memo(DeviceNodeComponent);
