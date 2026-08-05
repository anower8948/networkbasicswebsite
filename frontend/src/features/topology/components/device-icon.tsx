/**
 * Device iconography.
 *
 * Drawn with `lucide-react` primitives rather than bitmap assets: they inherit
 * `currentColor`, stay crisp at any zoom level on the canvas, and add nothing
 * to the bundle beyond the icons already in use.
 *
 * Colour encodes the OSI layer a device works at — endpoints one hue,
 * switching another, routing another — so the canvas reads at a glance.
 */

import {
  Cloud,
  Globe,
  HardDrive,
  Laptop,
  Monitor,
  Network,
  Phone,
  Printer,
  Radio,
  Router,
  Server,
  Shield,
  Video,
  Wifi,
  Cpu,
  Layers3,
} from 'lucide-react';

import type { DeviceKind } from '@/types/topology';

const ICONS: Record<DeviceKind, typeof Monitor> = {
  pc: Monitor,
  laptop: Laptop,
  server: Server,
  router: Router,
  switch: Network,
  multilayer_switch: Layers3,
  firewall: Shield,
  wireless_router: Wifi,
  access_point: Radio,
  cloud: Cloud,
  isp: Globe,
  nas: HardDrive,
  printer: Printer,
  camera: Video,
  ip_phone: Phone,
  iot: Cpu,
};

interface DeviceIconProps {
  kind: DeviceKind;
  className?: string;
}

export function DeviceIcon({ kind, className }: DeviceIconProps) {
  const Icon = ICONS[kind];
  return <Icon className={className} aria-hidden />;
}
