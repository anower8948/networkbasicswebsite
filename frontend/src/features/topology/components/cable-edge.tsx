/**
 * A cable between two devices.
 *
 * Cable type is encoded in the line itself, matching how network diagrams are
 * conventionally drawn: solid for straight-through, dashed for crossover,
 * dotted for wireless, thick amber for serial, and a light-blue line for fibre.
 * A learner should be able to read the cabling without clicking anything.
 */

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';
import { motion } from 'motion/react';
import { memo } from 'react';

import type { CableKind } from '@/types/topology';

export interface CableEdgeData extends Record<string, unknown> {
  cable: CableKind;
  /** Set while a simulated packet is crossing this link. */
  packet?: { label: string; reversed: boolean; ok: boolean } | null;
  enabled: boolean;
  sourceInterface: string;
  targetInterface: string;
  label: string | null;
  warning: string | null;
}

interface CableStyle {
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
}

const CABLE_STYLES: Record<CableKind, CableStyle> = {
  straight_through: { stroke: 'oklch(0.55 0.02 250)', strokeWidth: 2 },
  crossover: { stroke: 'oklch(0.55 0.02 250)', strokeWidth: 2, strokeDasharray: '7 4' },
  fiber: { stroke: 'oklch(0.65 0.16 210)', strokeWidth: 2.5 },
  serial: { stroke: 'oklch(0.68 0.15 70)', strokeWidth: 3 },
  console: { stroke: 'oklch(0.60 0.04 250)', strokeWidth: 1.5, strokeDasharray: '2 3' },
  wireless: { stroke: 'oklch(0.62 0.16 295)', strokeWidth: 2, strokeDasharray: '2 5' },
};

function CableEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const edge = (data ?? {}) as Partial<CableEdgeData>;
  const cable = edge.cable ?? 'straight_through';
  const style = CABLE_STYLES[cable];

  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 12,
  });

  // A disabled link is drawn faint — Part 8 injects failures this way, and the
  // learner should see a cable that exists but is down.
  const isDown = edge.enabled === false;
  const stroke = edge.warning ? 'var(--color-warning)' : style.stroke;

  const packet = edge.packet ?? null;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: selected ? 'var(--color-accent-500)' : stroke,
          strokeWidth: selected ? style.strokeWidth + 1 : style.strokeWidth,
          ...(style.strokeDasharray ? { strokeDasharray: style.strokeDasharray } : {}),
          opacity: isDown ? 0.35 : 1,
        }}
      />

      {/* The packet rides the real edge path, so it follows every bend the
          cable takes rather than cutting across the canvas. */}
      {packet && (
        <>
          <circle
            r={7}
            fill={packet.ok ? 'var(--color-accent-500)' : 'var(--color-danger)'}
            stroke="var(--surface-raised)"
            strokeWidth={2}
          >
            <animateMotion
              dur="0.85s"
              repeatCount="indefinite"
              path={path}
              keyPoints={packet.reversed ? '1;0' : '0;1'}
              keyTimes="0;1"
              calcMode="linear"
            />
          </circle>
        </>
      )}

      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="pointer-events-none flex flex-col items-center gap-0.5"
        >
          {edge.warning && (
            <span
              title={edge.warning}
              className="rounded-full bg-[var(--color-warning)] px-1.5 py-0.5 text-[9px] font-bold text-white"
            >
              !
            </span>
          )}
          {packet && (
            <motion.span
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-[var(--radius-xs)] bg-accent-500 px-1.5 py-0.5 text-[10px] font-medium text-white shadow-sm"
            >
              {packet.label}
            </motion.span>
          )}
          {edge.label && (
            <span className="rounded-[var(--radius-xs)] bg-[var(--surface-raised)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] shadow-sm">
              {edge.label}
            </span>
          )}
          {isDown && (
            <span className="rounded-[var(--radius-xs)] bg-[var(--surface-raised)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)] shadow-sm">
              down
            </span>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const CableEdge = memo(CableEdgeComponent);
export { CABLE_STYLES };
