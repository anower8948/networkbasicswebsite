/**
 * The configuration window seeds its working `DeviceConfig` from the device on
 * mount. That makes it a state-outlives-its-subject hazard: if the same
 * instance is ever reused for a different device, the next edit writes the old
 * device's configuration over the new one and silently wipes its interfaces.
 *
 * This was a real bug, found in browser verification during Part 8. The fix is
 * a `key` on the device id at the call site, and this test is what stops it
 * coming back.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { cloneElement, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { DeviceConfigWindow } from './device-config-window';
import type { DeviceSpec, TopologyDevice, TopologyDocument } from '@/types/topology';

vi.mock('../api/device-api', () => ({
  deviceApi: {
    saveConfig: vi.fn().mockResolvedValue({ warnings: [], config: {} }),
    views: vi.fn().mockResolvedValue({ runningConfig: '', interfaceBrief: '', ipRoute: '' }),
  },
}));

const pcSpec: DeviceSpec = {
  kind: 'pc',
  label: 'PC',
  model: 'Generic desktop',
  description: '',
  osiLayer: 7,
  hasCli: false,
  isEndpoint: true,
  interfaces: [{ name: 'Ethernet0', shortName: 'eth0', kind: 'ethernet', connectable: true }],
};

const pc1: TopologyDevice = {
  id: 'pc1',
  kind: 'pc',
  name: 'PC1',
  position: { x: 0, y: 0 },
  label: null,
  groupId: null,
  config: { defaultGateway: '192.168.1.1' },
};

const pc2: TopologyDevice = {
  id: 'pc2',
  kind: 'pc',
  name: 'PC2',
  position: { x: 100, y: 0 },
  label: null,
  groupId: null,
  config: { defaultGateway: '10.0.0.1' },
};

const emptyDocument: TopologyDocument = {
  schemaVersion: 1,
  devices: [pc1, pc2],
  links: [],
  groups: [],
  viewport: { x: 0, y: 0, zoom: 1 },
};

/** Mimics the workspace: one window, whichever device is selected. */
function Harness({ keyed, onChange }: { keyed: boolean; onChange: (id: string, config: unknown) => void }) {
  const [deviceId, setDeviceId] = useState('pc1');
  const device = deviceId === 'pc1' ? pc1 : pc2;

  const window = (
    <DeviceConfigWindow
      document={emptyDocument}
      device={device}
      spec={pcSpec}
      onChange={(config) => onChange(device.id, config)}
      onClose={() => {}}
    />
  );

  return (
    <>
      <button type="button" onClick={() => setDeviceId('pc2')}>
        Switch to PC2
      </button>
      {/* `cloneElement` rather than a spread: React rejects `key` inside props. */}
      {keyed ? cloneElement(window, { key: device.id }) : window}
    </>
  );
}

function renderHarness(keyed: boolean) {
  const onChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Harness keyed={keyed} onChange={onChange} />
    </QueryClientProvider>,
  );
  return { onChange };
}

describe('DeviceConfigWindow', () => {
  it('seeds its fields from the device it was opened for', () => {
    renderHarness(true);

    expect(screen.getByLabelText('Default gateway')).toHaveValue('192.168.1.1');
  });

  it('re-seeds when keyed and the device changes', async () => {
    renderHarness(true);

    await userEvent.click(screen.getByRole('button', { name: 'Switch to PC2' }));

    expect(screen.getByLabelText('Default gateway')).toHaveValue('10.0.0.1');
  });

  it('reports edits against the device that is open', async () => {
    const { onChange } = renderHarness(true);

    await userEvent.click(screen.getByRole('button', { name: 'Switch to PC2' }));
    await userEvent.type(screen.getByLabelText('Hostname'), 'B');

    const [deviceId, config] = onChange.mock.calls.at(-1) as [string, { defaultGateway?: string }];
    expect(deviceId).toBe('pc2');
    // The gateway written back must be PC2's, not the one PC1 was showing.
    expect(config.defaultGateway).toBe('10.0.0.1');
  });

  it('without a key it carries the previous device’s config across', async () => {
    // Documents *why* the key is required: this is the bug, reproduced.
    const { onChange } = renderHarness(false);

    await userEvent.click(screen.getByRole('button', { name: 'Switch to PC2' }));
    await userEvent.type(screen.getByLabelText('Hostname'), 'B');

    const [deviceId, config] = onChange.mock.calls.at(-1) as [string, { defaultGateway?: string }];
    expect(deviceId).toBe('pc2');
    expect(config.defaultGateway).toBe('192.168.1.1');
  });
});
