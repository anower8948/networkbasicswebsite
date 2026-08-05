/** Device configuration and CLI types. Mirrors the backend schemas. */

/*
 * Optional fields spell out `| undefined` because `exactOptionalPropertyTypes`
 * is on and these objects are assembled by spreading partial updates.
 */

export type SwitchportMode = 'access' | 'trunk';
export type DuplexSetting = 'auto' | 'full' | 'half';
export type SpeedSetting = 'auto' | '10' | '100' | '1000';

export interface InterfaceConfig {
  description?: string | null | undefined;
  ipAddress?: string | null | undefined;
  subnetMask?: string | null | undefined;
  dhcp?: boolean;
  /** Interfaces are administratively down until `no shutdown`, as on real gear. */
  enabled?: boolean;
  speed?: SpeedSetting;
  duplex?: DuplexSetting;
  switchportMode?: SwitchportMode | null | undefined;
  accessVlan?: number | null | undefined;
  voiceVlan?: number | null | undefined;
  nativeVlan?: number | null | undefined;
  allowedVlans?: number[];
  natSide?: 'inside' | 'outside' | null | undefined;
  aclIn?: string | null | undefined;
  aclOut?: string | null | undefined;
}

export interface VlanConfig {
  id: number;
  name: string;
}

export interface StaticRoute {
  network: string;
  mask: string;
  nextHop?: string | null | undefined;
  exitInterface?: string | null | undefined;
  distance?: number;
}

export interface OspfNetwork {
  network: string;
  wildcard: string;
  area: number;
}

export interface OspfConfig {
  processId: number;
  routerId?: string | null | undefined;
  networks: OspfNetwork[];
  passiveInterfaces: string[];
}

export interface EigrpNetwork {
  network: string;
  wildcard?: string | null | undefined;
}

export interface EigrpConfig {
  asNumber: number;
  routerId?: string | null | undefined;
  networks: EigrpNetwork[];
  autoSummary: boolean;
}

export interface RipConfig {
  version: 1 | 2;
  networks: string[];
  autoSummary: boolean;
}

export interface DhcpPool {
  name: string;
  network: string;
  mask: string;
  gateway?: string | null | undefined;
  dnsServers: string[];
  domainName?: string | null | undefined;
  leaseHours?: number;
  excludedStart?: string | null | undefined;
  excludedEnd?: string | null | undefined;
}

export interface AclEntry {
  sequence: number;
  action: 'permit' | 'deny';
  protocol: 'ip' | 'tcp' | 'udp' | 'icmp';
  source: string;
  sourceWildcard?: string | null | undefined;
  destination: string;
  destinationWildcard?: string | null | undefined;
  destinationPort?: number | null | undefined;
  portOperator?: 'eq' | 'gt' | 'lt' | 'neq' | null | undefined;
}

export interface AclConfig {
  name: string;
  kind: 'standard' | 'extended';
  entries: AclEntry[];
}

export interface NatRule {
  kind: 'static' | 'dynamic' | 'overload';
  insideLocal?: string | null | undefined;
  insideGlobal?: string | null | undefined;
  accessList?: string | null | undefined;
  poolName?: string | null | undefined;
  interface?: string | null | undefined;
}

export interface WirelessConfig {
  ssid: string;
  security: 'open' | 'wep' | 'wpa2-psk' | 'wpa3-psk';
  passphrase: string;
  channel: number;
  band: '2.4' | '5';
  broadcastSsid: boolean;
}

/**
 * A device's whole configuration.
 *
 * The configuration forms and the CLI both read and write this one object, so
 * a change made either way is immediately visible to the other.
 */
export interface DeviceConfig {
  hostname?: string;
  enableSecret?: string | null | undefined;
  bannerMotd?: string | null | undefined;
  interfaces?: Record<string, InterfaceConfig>;
  defaultGateway?: string | null | undefined;
  dnsServers?: string[];
  dhcpClient?: boolean;
  vlans?: VlanConfig[];
  staticRoutes?: StaticRoute[];
  ospf?: OspfConfig | null | undefined;
  eigrp?: EigrpConfig | null | undefined;
  rip?: RipConfig | null | undefined;
  dhcpPools?: DhcpPool[];
  acls?: AclConfig[];
  natRules?: NatRule[];
  wireless?: WirelessConfig | null | undefined;
  saved?: boolean;
}

export const EMPTY_CONFIG: DeviceConfig = {};

/* -------------------------------------------------------------------------- */
/* CLI                                                                         */
/* -------------------------------------------------------------------------- */

export type CliMode =
  | 'user_exec'
  | 'priv_exec'
  | 'global_config'
  | 'interface_config'
  | 'vlan_config'
  | 'router_config'
  | 'line_config'
  | 'dhcp_config';

/** Where the operator currently is. Held by the terminal, sent with each line. */
export interface CliSession {
  mode: CliMode;
  interface?: string | null | undefined;
  vlanId?: number | null | undefined;
  routerProtocol?: string | null | undefined;
  routerProcess?: number | null | undefined;
  dhcpPool?: string | null | undefined;
  line?: string | null | undefined;
  hostname: string;
}

export interface CliResponse {
  output: string;
  session: CliSession;
  config: DeviceConfig;
  prompt: string;
  changed: boolean;
}

export interface DeviceConfigResponse {
  deviceId: string;
  config: DeviceConfig;
  runningConfig: string;
  warnings: string[];
}

export interface DeviceViewResponse {
  runningConfig: string;
  interfaceBrief: string;
  ipRoute: string;
}

export function initialSession(hostname = 'Router'): CliSession {
  return { mode: 'user_exec', hostname };
}
