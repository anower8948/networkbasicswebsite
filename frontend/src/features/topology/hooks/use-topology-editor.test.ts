import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useTopologyEditor } from './use-topology-editor';
import { EMPTY_DOCUMENT, type DeviceSpec, type TopologyDocument } from '@/types/topology';

const catalog: DeviceSpec[] = [
  {
    kind: 'pc',
    label: 'PC',
    model: 'Generic desktop',
    description: '',
    osiLayer: 7,
    hasCli: false,
    isEndpoint: true,
    interfaces: [
      { name: 'Ethernet0', shortName: 'eth0', kind: 'ethernet', connectable: true },
    ],
  },
  {
    kind: 'switch',
    label: 'Switch',
    model: 'Catalyst 2960',
    description: '',
    osiLayer: 2,
    hasCli: true,
    isEndpoint: false,
    interfaces: [
      { name: 'FastEthernet0/1', shortName: 'fa0/1', kind: 'fast_ethernet', connectable: true },
      { name: 'FastEthernet0/2', shortName: 'fa0/2', kind: 'fast_ethernet', connectable: true },
      { name: 'Console0', shortName: 'con0', kind: 'console', connectable: false },
    ],
  },
];

function setup(initial: TopologyDocument = EMPTY_DOCUMENT) {
  return renderHook(() => useTopologyEditor(initial, catalog));
}

describe('useTopologyEditor', () => {
  describe('devices', () => {
    it('adds a device with an auto-generated name', () => {
      const { result } = setup();

      act(() => {
        result.current.addDevice('pc', { x: 10, y: 20 });
      });

      expect(result.current.document.devices).toHaveLength(1);
      expect(result.current.document.devices[0]?.name).toBe('PC1');
      expect(result.current.isDirty).toBe(true);
    });

    it('numbers devices of the same kind sequentially', () => {
      const { result } = setup();

      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });
      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });
      act(() => {
        result.current.addDevice('switch', { x: 0, y: 0 });
      });

      expect(result.current.document.devices.map((d) => d.name)).toEqual(['PC1', 'PC2', 'SW1']);
    });

    it('renames a device', () => {
      const { result } = setup();
      let id = '';
      act(() => {
        id = result.current.addDevice('pc', { x: 0, y: 0 }).id;
      });

      act(() => {
        result.current.renameDevice(id, 'Reception-PC');
      });

      expect(result.current.document.devices[0]?.name).toBe('Reception-PC');
    });

    it('removes a device together with its cables', () => {
      // A link to a removed device would fail the server's validation.
      const { result } = setup();
      let pcId = '';
      let swId = '';
      act(() => {
        pcId = result.current.addDevice('pc', { x: 0, y: 0 }).id;
        swId = result.current.addDevice('switch', { x: 200, y: 0 }).id;
      });
      act(() => {
        result.current.addLink({
          source: { deviceId: pcId, interface: 'Ethernet0' },
          target: { deviceId: swId, interface: 'FastEthernet0/1' },
          cable: 'straight_through',
          enabled: true,
          label: null,
        });
      });
      expect(result.current.document.links).toHaveLength(1);

      act(() => {
        result.current.removeDevice(pcId);
      });

      expect(result.current.document.devices).toHaveLength(1);
      expect(result.current.document.links).toHaveLength(0);
    });
  });

  describe('interface availability', () => {
    it('reports free interfaces, excluding those already cabled', () => {
      const { result } = setup();
      let pcId = '';
      let swId = '';
      act(() => {
        pcId = result.current.addDevice('pc', { x: 0, y: 0 }).id;
        swId = result.current.addDevice('switch', { x: 200, y: 0 }).id;
      });
      act(() => {
        result.current.addLink({
          source: { deviceId: pcId, interface: 'Ethernet0' },
          target: { deviceId: swId, interface: 'FastEthernet0/1' },
          cable: 'straight_through',
          enabled: true,
          label: null,
        });
      });

      expect(result.current.freeInterfacesFor(pcId)).toEqual([]);
      expect(result.current.freeInterfacesFor(swId)).toEqual(['FastEthernet0/2']);
    });

    it('never offers a console port', () => {
      const { result } = setup();
      let swId = '';
      act(() => {
        swId = result.current.addDevice('switch', { x: 0, y: 0 }).id;
      });

      expect(result.current.freeInterfacesFor(swId)).not.toContain('Console0');
    });
  });

  describe('groups', () => {
    it('clears membership when a group is removed', () => {
      // A dangling groupId would fail server validation.
      const { result } = setup();
      let deviceId = '';
      act(() => {
        deviceId = result.current.addDevice('pc', { x: 0, y: 0 }).id;
        result.current.addGroup('Floor 1', { x: 0, y: 0 });
      });
      const groupId = result.current.document.groups[0]?.id as string;
      act(() => {
        result.current.assignToGroup(deviceId, groupId);
      });
      expect(result.current.document.devices[0]?.groupId).toBe(groupId);

      act(() => {
        result.current.removeGroup(groupId);
      });

      expect(result.current.document.groups).toHaveLength(0);
      expect(result.current.document.devices[0]?.groupId).toBeNull();
    });
  });

  describe('history', () => {
    it('undoes and redoes an edit', () => {
      const { result } = setup();
      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });
      expect(result.current.document.devices).toHaveLength(1);

      act(() => {
        result.current.undo();
      });
      expect(result.current.document.devices).toHaveLength(0);

      act(() => {
        result.current.redo();
      });
      expect(result.current.document.devices).toHaveLength(1);
    });

    it('reports whether undo and redo are available', () => {
      const { result } = setup();
      expect(result.current.canUndo).toBe(false);

      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });
      expect(result.current.canUndo).toBe(true);
      expect(result.current.canRedo).toBe(false);

      act(() => {
        result.current.undo();
      });
      expect(result.current.canRedo).toBe(true);
    });

    it('discards the redo stack after a new edit', () => {
      const { result } = setup();
      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });
      act(() => {
        result.current.undo();
      });
      expect(result.current.canRedo).toBe(true);

      act(() => {
        result.current.addDevice('switch', { x: 0, y: 0 });
      });

      expect(result.current.canRedo).toBe(false);
    });

    it('treats a whole drag as one undo step', () => {
      // Position updates fire per animation frame; undo must rewind the drag,
      // not one frame of it.
      const { result } = setup();
      let id = '';
      act(() => {
        id = result.current.addDevice('pc', { x: 0, y: 0 }).id;
      });

      act(() => {
        result.current.moveDevice(id, { x: 10, y: 10 });
      });
      act(() => {
        result.current.moveDevice(id, { x: 40, y: 40 });
      });
      act(() => {
        result.current.moveDevice(id, { x: 90, y: 90 });
        result.current.commitMove();
      });
      expect(result.current.document.devices[0]?.position).toEqual({ x: 90, y: 90 });

      act(() => {
        result.current.undo();
      });

      expect(result.current.document.devices[0]?.position).toEqual({ x: 0, y: 0 });
    });
  });

  describe('save state', () => {
    it('starts clean and becomes dirty on the first edit', () => {
      const { result } = setup();
      expect(result.current.isDirty).toBe(false);

      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });

      expect(result.current.isDirty).toBe(true);
    });

    it('is clean again after a save', () => {
      const { result } = setup();
      act(() => {
        result.current.addDevice('pc', { x: 0, y: 0 });
      });

      act(() => {
        result.current.markSaved();
      });

      expect(result.current.isDirty).toBe(false);
    });

    it('does not mark the document dirty when only panning', () => {
      // Panning is navigation, not an edit — it must not prompt to save.
      const { result } = setup();

      act(() => {
        result.current.setViewport({ x: 120, y: -40, zoom: 1.5 });
      });

      expect(result.current.isDirty).toBe(false);
      expect(result.current.document.viewport.zoom).toBe(1.5);
    });
  });
});
