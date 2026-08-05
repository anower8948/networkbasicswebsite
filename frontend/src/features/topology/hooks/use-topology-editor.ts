/**
 * Editor state for one topology document.
 *
 * The document is the single source of truth; React Flow nodes and edges are
 * *derived* from it on every render rather than kept in parallel. Holding both
 * and syncing them is the classic way these editors rot — a drag updates one
 * copy, a save reads the other, and they disagree.
 *
 * Undo/redo is a bounded stack of whole documents. Documents are small (a few
 * kilobytes even at the 200-device ceiling), so snapshotting is far simpler
 * than inverse operations and cannot drift from the real state.
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import type {
  CableKind,
  DeviceKind,
  DeviceSpec,
  Position,
  TopologyDevice,
  TopologyDocument,
  TopologyLink,
} from '@/types/topology';

const HISTORY_LIMIT = 50;

/** Short unique id — collision-safe within one document. */
function newId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Next free name for a device kind: PC1, PC2, R1, SW1… */
function nextDeviceName(document: TopologyDocument, kind: DeviceKind): string {
  const prefixes: Partial<Record<DeviceKind, string>> = {
    pc: 'PC',
    laptop: 'LT',
    server: 'SRV',
    router: 'R',
    switch: 'SW',
    multilayer_switch: 'MLS',
    firewall: 'FW',
    wireless_router: 'WR',
    access_point: 'AP',
    cloud: 'CLOUD',
    isp: 'ISP',
    nas: 'NAS',
    printer: 'PRN',
    camera: 'CAM',
    ip_phone: 'PHONE',
    iot: 'IOT',
  };
  const prefix = prefixes[kind] ?? 'DEV';

  const used = new Set(document.devices.map((device) => device.name));
  let index = 1;
  while (used.has(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}

export interface TopologyEditor {
  document: TopologyDocument;
  isDirty: boolean;
  canUndo: boolean;
  canRedo: boolean;

  addDevice: (kind: DeviceKind, position: Position) => TopologyDevice;
  moveDevice: (deviceId: string, position: Position) => void;
  /** Position updates during a drag; not recorded in history until it ends. */
  commitMove: () => void;
  renameDevice: (deviceId: string, name: string) => void;
  labelDevice: (deviceId: string, label: string | null) => void;
  removeDevice: (deviceId: string) => void;
  /** Replace a device's configuration (Part 5 forms and the Part 6 CLI). */
  configureDevice: (deviceId: string, config: Record<string, unknown>) => void;

  addLink: (link: Omit<TopologyLink, 'id'>) => TopologyLink;
  updateLink: (linkId: string, changes: Partial<Omit<TopologyLink, 'id'>>) => void;
  removeLink: (linkId: string) => void;

  addGroup: (name: string, position: Position) => void;
  renameGroup: (groupId: string, name: string) => void;
  removeGroup: (groupId: string) => void;
  assignToGroup: (deviceId: string, groupId: string | null) => void;

  setViewport: (viewport: TopologyDocument['viewport']) => void;
  replaceDocument: (document: TopologyDocument, options?: { markClean?: boolean }) => void;
  markSaved: () => void;
  undo: () => void;
  redo: () => void;

  /** Interfaces already carrying a link, keyed `deviceId::interface`. */
  occupiedInterfaces: Set<string>;
  freeInterfacesFor: (deviceId: string) => string[];
}

export function useTopologyEditor(
  initial: TopologyDocument,
  catalog: DeviceSpec[],
): TopologyEditor {
  const [document, setDocument] = useState<TopologyDocument>(initial);
  const [isDirty, setIsDirty] = useState(false);

  const past = useRef<TopologyDocument[]>([]);
  const future = useRef<TopologyDocument[]>([]);
  const [historyVersion, setHistoryVersion] = useState(0);

  const specByKind = useMemo(
    () => new Map(catalog.map((spec) => [spec.kind, spec])),
    [catalog],
  );

  /** Apply a change, pushing the previous document onto the undo stack. */
  const commit = useCallback(
    (mutate: (current: TopologyDocument) => TopologyDocument) => {
      setDocument((current) => {
        past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), current];
        future.current = [];
        return mutate(current);
      });
      setIsDirty(true);
      setHistoryVersion((value) => value + 1);
    },
    [],
  );

  /** Apply a change *without* touching history — used during a drag. */
  const applyTransient = useCallback(
    (mutate: (current: TopologyDocument) => TopologyDocument) => {
      setDocument(mutate);
      setIsDirty(true);
    },
    [],
  );

  const dragOrigin = useRef<TopologyDocument | null>(null);

  const addDevice = useCallback(
    (kind: DeviceKind, position: Position): TopologyDevice => {
      const device: TopologyDevice = {
        id: newId(kind),
        kind,
        name: nextDeviceName(document, kind),
        position,
        label: null,
        groupId: null,
        config: {},
      };
      commit((current) => ({ ...current, devices: [...current.devices, device] }));
      return device;
    },
    [commit, document],
  );

  const moveDevice = useCallback(
    (deviceId: string, position: Position) => {
      // Capture the pre-drag document once, so the whole drag is a single
      // undo step rather than one per animation frame.
      dragOrigin.current ??= document;
      applyTransient((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === deviceId ? { ...device, position } : device,
        ),
      }));
    },
    [applyTransient, document],
  );

  const commitMove = useCallback(() => {
    const origin = dragOrigin.current;
    dragOrigin.current = null;
    if (!origin) return;
    past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), origin];
    future.current = [];
    setHistoryVersion((value) => value + 1);
  }, []);

  const renameDevice = useCallback(
    (deviceId: string, name: string) => {
      commit((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === deviceId ? { ...device, name } : device,
        ),
      }));
    },
    [commit],
  );

  const labelDevice = useCallback(
    (deviceId: string, label: string | null) => {
      commit((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === deviceId ? { ...device, label } : device,
        ),
      }));
    },
    [commit],
  );

  const removeDevice = useCallback(
    (deviceId: string) => {
      // Links to a removed device must go too, or the document fails the
      // server's structural validation on the next save.
      commit((current) => ({
        ...current,
        devices: current.devices.filter((device) => device.id !== deviceId),
        links: current.links.filter(
          (link) => link.source.deviceId !== deviceId && link.target.deviceId !== deviceId,
        ),
      }));
    },
    [commit],
  );

  const configureDevice = useCallback(
    (deviceId: string, config: Record<string, unknown>) => {
      commit((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === deviceId ? { ...device, config } : device,
        ),
      }));
    },
    [commit],
  );

  const addLink = useCallback(
    (link: Omit<TopologyLink, 'id'>): TopologyLink => {
      const created: TopologyLink = { ...link, id: newId('link') };
      commit((current) => ({ ...current, links: [...current.links, created] }));
      return created;
    },
    [commit],
  );

  const updateLink = useCallback(
    (linkId: string, changes: Partial<Omit<TopologyLink, 'id'>>) => {
      commit((current) => ({
        ...current,
        links: current.links.map((link) =>
          link.id === linkId ? { ...link, ...changes } : link,
        ),
      }));
    },
    [commit],
  );

  const removeLink = useCallback(
    (linkId: string) => {
      commit((current) => ({
        ...current,
        links: current.links.filter((link) => link.id !== linkId),
      }));
    },
    [commit],
  );

  const addGroup = useCallback(
    (name: string, position: Position) => {
      commit((current) => ({
        ...current,
        groups: [
          ...current.groups,
          { id: newId('group'), name, position, width: 380, height: 260, color: null },
        ],
      }));
    },
    [commit],
  );

  const renameGroup = useCallback(
    (groupId: string, name: string) => {
      commit((current) => ({
        ...current,
        groups: current.groups.map((group) =>
          group.id === groupId ? { ...group, name } : group,
        ),
      }));
    },
    [commit],
  );

  const removeGroup = useCallback(
    (groupId: string) => {
      // Devices survive; only their membership is cleared. A dangling groupId
      // would fail server validation.
      commit((current) => ({
        ...current,
        groups: current.groups.filter((group) => group.id !== groupId),
        devices: current.devices.map((device) =>
          device.groupId === groupId ? { ...device, groupId: null } : device,
        ),
      }));
    },
    [commit],
  );

  const assignToGroup = useCallback(
    (deviceId: string, groupId: string | null) => {
      commit((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === deviceId ? { ...device, groupId } : device,
        ),
      }));
    },
    [commit],
  );

  const setViewport = useCallback((viewport: TopologyDocument['viewport']) => {
    // Panning is not an edit: it neither marks the document dirty nor enters
    // history. It is persisted with the next real save.
    setDocument((current) => ({ ...current, viewport }));
  }, []);

  const replaceDocument = useCallback(
    (next: TopologyDocument, options?: { markClean?: boolean }) => {
      past.current = [];
      future.current = [];
      setDocument(next);
      setIsDirty(!options?.markClean);
      setHistoryVersion((value) => value + 1);
    },
    [],
  );

  const markSaved = useCallback(() => setIsDirty(false), []);

  const undo = useCallback(() => {
    const previous = past.current.at(-1);
    if (!previous) return;
    past.current = past.current.slice(0, -1);
    setDocument((current) => {
      future.current = [...future.current, current];
      return previous;
    });
    setIsDirty(true);
    setHistoryVersion((value) => value + 1);
  }, []);

  const redo = useCallback(() => {
    const next = future.current.at(-1);
    if (!next) return;
    future.current = future.current.slice(0, -1);
    setDocument((current) => {
      past.current = [...past.current, current];
      return next;
    });
    setIsDirty(true);
    setHistoryVersion((value) => value + 1);
  }, []);

  const occupiedInterfaces = useMemo(() => {
    const taken = new Set<string>();
    for (const link of document.links) {
      taken.add(`${link.source.deviceId}::${link.source.interface}`);
      taken.add(`${link.target.deviceId}::${link.target.interface}`);
    }
    return taken;
  }, [document.links]);

  const freeInterfacesFor = useCallback(
    (deviceId: string): string[] => {
      const device = document.devices.find((item) => item.id === deviceId);
      if (!device) return [];
      const spec = specByKind.get(device.kind);
      if (!spec) return [];

      return spec.interfaces
        .filter((entry) => entry.connectable)
        .map((entry) => entry.name)
        .filter((name) => !occupiedInterfaces.has(`${deviceId}::${name}`));
    },
    [document.devices, occupiedInterfaces, specByKind],
  );

  return {
    document,
    isDirty,
    // Read through `historyVersion` so these recompute when the refs mutate.
    canUndo: historyVersion >= 0 && past.current.length > 0,
    canRedo: historyVersion >= 0 && future.current.length > 0,
    addDevice,
    moveDevice,
    commitMove,
    renameDevice,
    labelDevice,
    removeDevice,
    configureDevice,
    addLink,
    updateLink,
    removeLink,
    addGroup,
    renameGroup,
    removeGroup,
    assignToGroup,
    setViewport,
    replaceDocument,
    markSaved,
    undo,
    redo,
    occupiedInterfaces,
    freeInterfacesFor,
  };
}

export const __testing = { newId, nextDeviceName };
export type { CableKind };
