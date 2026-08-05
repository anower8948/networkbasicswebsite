/**
 * Device colours, kept apart from the icon component.
 *
 * Colour encodes the OSI layer a device works at — endpoints one hue, switching
 * another, routing another — so the canvas reads at a glance. Separated from
 * `device-icon.tsx` because a module that exports both components and constants
 * defeats React Fast Refresh.
 */

import type { DeviceKind } from '@/types/topology';

/** Hue per device family, so the canvas is readable without labels. */
const COLORS: Record<DeviceKind, string> = {
  // Endpoints — blue.
  pc: 'oklch(0.62 0.16 250)',
  laptop: 'oklch(0.62 0.16 250)',
  printer: 'oklch(0.62 0.12 250)',
  camera: 'oklch(0.62 0.12 250)',
  ip_phone: 'oklch(0.62 0.12 250)',
  iot: 'oklch(0.62 0.12 250)',
  // Servers and storage — teal.
  server: 'oklch(0.62 0.14 195)',
  nas: 'oklch(0.62 0.14 195)',
  // Layer 2 — green.
  switch: 'oklch(0.62 0.16 155)',
  access_point: 'oklch(0.62 0.14 155)',
  // Layer 3 — violet.
  router: 'oklch(0.60 0.19 295)',
  multilayer_switch: 'oklch(0.60 0.17 295)',
  wireless_router: 'oklch(0.60 0.15 295)',
  // Security — red.
  firewall: 'oklch(0.60 0.19 25)',
  // External — grey-blue.
  cloud: 'oklch(0.58 0.05 250)',
  isp: 'oklch(0.58 0.08 250)',
};


export function deviceColor(kind: DeviceKind): string {
  return COLORS[kind];
}
