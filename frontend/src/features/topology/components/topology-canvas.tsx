/**
 * The React Flow canvas.
 *
 * Nodes and edges are **derived from the document on every render**, never held
 * as separate state. React Flow reports interactions (a drag, a new
 * connection); the document is updated and the canvas re-derives. Keeping two
 * copies in sync is how these editors accumulate bugs.
 */

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeTypes,
  type NodeTypes,
} from '@xyflow/react';
import { useCallback, useMemo, type DragEvent } from 'react';

import { CableEdge } from './cable-edge';
import { DeviceNode, type DeviceNodeData } from './device-node';
import { deviceColor } from './device-colors';
import type { TopologyEditor } from '../hooks/use-topology-editor';
import type { DeviceKind, DeviceSpec, LinkIssue } from '@/types/topology';

// Defined outside the component: React Flow warns (and re-instantiates every
// node) if these object identities change between renders.
const NODE_TYPES: NodeTypes = { device: DeviceNode };
const EDGE_TYPES: EdgeTypes = { cable: CableEdge };

interface TopologyCanvasProps {
  editor: TopologyEditor;
  catalog: DeviceSpec[];
  issues: LinkIssue[];
  selectedDeviceId: string | null;
  selectedLinkId: string | null;
  onSelectDevice: (deviceId: string | null) => void;
  onSelectLink: (linkId: string | null) => void;
  onConnect: (source: string, target: string) => void;
  onOpenDevice: (deviceId: string) => void;
  /** The link a simulated packet is crossing right now, if any. */
  activePacket?: {
    linkId: string;
    label: string;
    reversed: boolean;
    ok: boolean;
  } | null;
}

export function TopologyCanvas({
  editor,
  catalog,
  issues,
  selectedDeviceId,
  selectedLinkId,
  onSelectDevice,
  onSelectLink,
  onConnect,
  onOpenDevice,
  activePacket = null,
}: TopologyCanvasProps) {
  const { screenToFlowPosition } = useReactFlow();
  const { document } = editor;

  const portCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const link of document.links) {
      counts.set(link.source.deviceId, (counts.get(link.source.deviceId) ?? 0) + 1);
      counts.set(link.target.deviceId, (counts.get(link.target.deviceId) ?? 0) + 1);
    }
    return counts;
  }, [document.links]);

  const warnedLinkIds = useMemo(
    () => new Set(issues.map((issue) => issue.linkId)),
    [issues],
  );

  const warnedDeviceIds = useMemo(() => {
    const devices = new Set<string>();
    for (const link of document.links) {
      if (!warnedLinkIds.has(link.id)) continue;
      devices.add(link.source.deviceId);
      devices.add(link.target.deviceId);
    }
    return devices;
  }, [document.links, warnedLinkIds]);

  const specByKind = useMemo(
    () => new Map(catalog.map((spec) => [spec.kind, spec])),
    [catalog],
  );

  const nodes: Node[] = useMemo(
    () =>
      document.devices.map((device) => {
        const spec = specByKind.get(device.kind);
        const data: DeviceNodeData = {
          kind: device.kind,
          name: device.name,
          label: device.label ?? null,
          linkCount: portCounts.get(device.id) ?? 0,
          totalPorts: spec?.interfaces.filter((entry) => entry.connectable).length ?? 0,
          hasWarning: warnedDeviceIds.has(device.id),
        };
        return {
          id: device.id,
          type: 'device',
          position: device.position,
          data,
          selected: device.id === selectedDeviceId,
        };
      }),
    [document.devices, portCounts, selectedDeviceId, specByKind, warnedDeviceIds],
  );

  const edges: Edge[] = useMemo(
    () =>
      document.links.map((link) => ({
        id: link.id,
        type: 'cable',
        source: link.source.deviceId,
        target: link.target.deviceId,
        selected: link.id === selectedLinkId,
        data: {
          cable: link.cable,
          enabled: link.enabled,
          sourceInterface: link.source.interface,
          targetInterface: link.target.interface,
          label: link.label ?? null,
          warning: issues.find((issue) => issue.linkId === link.id)?.message ?? null,
          packet:
            activePacket && activePacket.linkId === link.id
              ? {
                  label: activePacket.label,
                  // The trace records which device sent it; the edge is drawn
                  // source→target, so a packet from the target runs backwards.
                  reversed: activePacket.reversed,
                  ok: activePacket.ok,
                }
              : null,
        },
      })),
    [activePacket, document.links, issues, selectedLinkId],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          editor.moveDevice(change.id, change.position);
          // React Flow reports `dragging: false` on the final frame — that is
          // when the whole drag becomes one undo step.
          if (change.dragging === false) editor.commitMove();
        }
        if (change.type === 'remove') {
          editor.removeDevice(change.id);
        }
      }
    },
    [editor],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      if (connection.source === connection.target) return; // no self-links
      onConnect(connection.source, connection.target);
    },
    [onConnect],
  );

  const handleDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const kind = event.dataTransfer.getData('application/nlp-device') as DeviceKind;
      if (!kind) return;

      // Translate the pointer into canvas coordinates so the device lands where
      // it was dropped regardless of pan and zoom.
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      editor.addDevice(kind, { x: Math.round(position.x - 52), y: Math.round(position.y - 40) });
    },
    [editor, screenToFlowPosition],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      onNodesChange={handleNodesChange}
      onConnect={handleConnect}
      onNodeClick={(_, node) => {
        onSelectDevice(node.id);
        onSelectLink(null);
      }}
      onNodeDoubleClick={(_, node) => onOpenDevice(node.id)}
      onEdgeClick={(_, edge) => {
        onSelectLink(edge.id);
        onSelectDevice(null);
      }}
      onPaneClick={() => {
        onSelectDevice(null);
        onSelectLink(null);
      }}
      onMoveEnd={(_, viewport) => editor.setViewport(viewport)}
      onDrop={handleDrop}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
      }}
      defaultViewport={document.viewport}
      minZoom={0.2}
      maxZoom={2.5}
      proOptions={{ hideAttribution: false }}
      deleteKeyCode={['Backspace', 'Delete']}
      className="bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="opacity-40" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(node) => deviceColor((node.data as DeviceNodeData).kind)}
        maskColor="oklch(0.5 0 0 / 0.12)"
        className="!bg-[var(--surface-raised)]"
      />
    </ReactFlow>
  );
}
