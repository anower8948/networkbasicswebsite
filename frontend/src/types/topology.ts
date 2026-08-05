/** Topology editor types. Mirrors `backend/app/schemas/topology.py`. */

export type DeviceKind =
  | 'pc'
  | 'laptop'
  | 'server'
  | 'router'
  | 'switch'
  | 'multilayer_switch'
  | 'firewall'
  | 'wireless_router'
  | 'access_point'
  | 'cloud'
  | 'isp'
  | 'nas'
  | 'printer'
  | 'camera'
  | 'ip_phone'
  | 'iot';

export type CableKind =
  | 'straight_through'
  | 'crossover'
  | 'fiber'
  | 'console'
  | 'serial'
  | 'wireless';

export type PortKind =
  | 'ethernet'
  | 'fast_ethernet'
  | 'gigabit_ethernet'
  | 'ten_gigabit'
  | 'serial'
  | 'console'
  | 'wireless'
  | 'sfp';

/* -------------------------------------------------------------------------- */
/* Device catalogue                                                            */
/* -------------------------------------------------------------------------- */

export interface DeviceInterface {
  name: string;
  shortName: string;
  kind: PortKind;
  /** False for console ports, which carry no traffic. */
  connectable: boolean;
}

export interface DeviceSpec {
  kind: DeviceKind;
  label: string;
  model: string;
  description: string;
  osiLayer: number;
  hasCli: boolean;
  isEndpoint: boolean;
  interfaces: DeviceInterface[];
}

/* -------------------------------------------------------------------------- */
/* Document                                                                    */
/* -------------------------------------------------------------------------- */

export interface Position {
  x: number;
  y: number;
}

export interface TopologyDevice {
  id: string;
  kind: DeviceKind;
  name: string;
  position: Position;
  label?: string | null;
  groupId?: string | null;
  /** Typed in Part 5; opaque here so the editor round-trips it untouched. */
  config: Record<string, unknown>;
}

export interface LinkEndpoint {
  deviceId: string;
  interface: string;
}

export interface TopologyLink {
  id: string;
  source: LinkEndpoint;
  target: LinkEndpoint;
  cable: CableKind;
  enabled: boolean;
  label?: string | null;
}

export interface TopologyGroup {
  id: string;
  name: string;
  position: Position;
  width: number;
  height: number;
  color?: string | null;
}

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

export interface TopologyDocument {
  schemaVersion: number;
  devices: TopologyDevice[];
  links: TopologyLink[];
  groups: TopologyGroup[];
  viewport: Viewport;
}

/** An advisory cabling problem — never blocks saving. */
export interface LinkIssue {
  linkId: string;
  message: string;
}

export interface TopologySummary {
  id: string;
  name: string;
  description: string | null;
  deviceCount: number;
  schemaVersion: number;
  isTemplate: boolean;
  isPublic: boolean;
  thumbnailUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TopologyRead extends TopologySummary {
  document: TopologyDocument;
  issues: LinkIssue[];
}

export interface LinkSuggestion {
  sourceInterface: string;
  targetInterface: string;
  cable: CableKind;
  warning: string | null;
}

export const EMPTY_DOCUMENT: TopologyDocument = {
  schemaVersion: 1,
  devices: [],
  links: [],
  groups: [],
  viewport: { x: 0, y: 0, zoom: 1 },
};

export const CABLE_LABELS: Record<CableKind, string> = {
  straight_through: 'Straight-through',
  crossover: 'Crossover',
  fiber: 'Fibre',
  console: 'Console',
  serial: 'Serial',
  wireless: 'Wireless',
};
