/** Packet simulation types. Mirrors `app/services/simulation/trace.py`. */

import type { TopologyDocument } from './topology';

export type SimulationProtocol =
  | 'ping'
  | 'traceroute'
  | 'arp'
  | 'dhcp'
  | 'dns'
  | 'tcp'
  | 'udp';

export type EventKind =
  | 'arp_request'
  | 'arp_reply'
  | 'arp_cached'
  | 'switch_flood'
  | 'switch_forward'
  | 'switch_learn'
  | 'route_lookup'
  | 'forward'
  | 'deliver'
  | 'reply'
  | 'dhcp_discover'
  | 'dhcp_offer'
  | 'dhcp_request'
  | 'dhcp_ack'
  | 'dns_query'
  | 'dns_response'
  | 'tcp_syn'
  | 'tcp_syn_ack'
  | 'tcp_ack'
  | 'tcp_data'
  | 'tcp_fin'
  | 'udp_datagram'
  | 'drop'
  | 'timeout'
  | 'note';

/**
 * Headers as they stand at one hop.
 *
 * MACs change every hop while the IPs do not — showing both side by side is
 * the clearest way to teach the difference.
 */
export interface FrameSummary {
  sourceMac: string | null;
  destinationMac: string | null;
  sourceIp: string | null;
  destinationIp: string | null;
  protocol: string | null;
  ttl: number | null;
  vlan: number | null;
}

export interface TraceEvent {
  step: number;
  kind: EventKind;
  deviceId: string;
  deviceName: string;
  interface: string | null;
  /** Present when the step crosses a cable — this is what the canvas animates. */
  linkId: string | null;
  toDeviceId: string | null;
  toInterface: string | null;
  summary: string;
  detail: string | null;
  frame: FrameSummary | null;
  ok: boolean;
}

export interface SimulationResult {
  success: boolean;
  protocol: string;
  summary: string;
  failureReason: string | null;
  hint: string | null;
  events: TraceEvent[];
}

export interface SimulationRequest {
  document: TopologyDocument;
  sourceDeviceId: string;
  protocol: SimulationProtocol;
  destination?: string;
  port?: number;
  count?: number;
}

export const PROTOCOL_LABELS: Record<SimulationProtocol, string> = {
  ping: 'Ping (ICMP)',
  traceroute: 'Traceroute',
  arp: 'ARP',
  dhcp: 'DHCP',
  dns: 'DNS',
  tcp: 'TCP',
  udp: 'UDP',
};

/** Protocols that broadcast rather than target an address. */
export const PROTOCOLS_WITHOUT_DESTINATION: SimulationProtocol[] = ['dhcp'];
