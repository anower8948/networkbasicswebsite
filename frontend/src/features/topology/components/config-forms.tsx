/**
 * Configuration forms.
 *
 * These edit the same `DeviceConfig` the CLI writes to, so anything set here
 * appears in `show running-config` and vice versa.
 *
 * Which forms are shown depends on what the device actually is: a PC gets
 * addressing and DNS, a switch gets VLANs, a router gets routing and services.
 * Showing a VLAN database on a PC would teach the wrong model.
 */

import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';
import type {
  DeviceConfig,
  InterfaceConfig,
  StaticRoute,
  VlanConfig,
} from '@/types/device-config';
import type { DeviceSpec } from '@/types/topology';

export type ConfigPatch = (previous: DeviceConfig) => DeviceConfig;

interface FormProps {
  config: DeviceConfig;
  spec: DeviceSpec;
  onChange: (patch: ConfigPatch) => void;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-[var(--text-secondary)]">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-[var(--text-tertiary)]">{hint}</span>}
    </div>
  );
}

const selectClass =
  'glass-inset h-9 w-full rounded-[var(--radius-sm)] px-2.5 text-[13px] focus:border-accent-500 focus:outline-none';

/* -------------------------------------------------------------------------- */
/* Interfaces                                                                  */
/* -------------------------------------------------------------------------- */
export function InterfaceForm({ config, spec, onChange }: FormProps) {
  const connectable = spec.interfaces.filter((entry) => entry.connectable);

  const patchInterface = (name: string, changes: Partial<InterfaceConfig>) =>
    onChange((previous) => ({
      ...previous,
      interfaces: {
        ...previous.interfaces,
        [name]: { ...previous.interfaces?.[name], ...changes },
      },
    }));

  return (
    <div className="flex flex-col gap-4">
      {connectable.map((entry) => {
        const current = config.interfaces?.[entry.name] ?? {};
        const isSwitchPort = entry.kind === 'fast_ethernet' || entry.kind === 'gigabit_ethernet';

        return (
          <div
            key={entry.name}
            className="rounded-[var(--radius-md)] border border-[var(--hairline)] p-3.5"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[13px] font-semibold">{entry.name}</span>
              <label className="flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={current.enabled ?? false}
                  onChange={(event) =>
                    patchInterface(entry.name, { enabled: event.target.checked })
                  }
                  className="size-3.5 accent-[var(--color-accent-500)]"
                  // The visible label reads "no shutdown" on every interface;
                  // qualifying it by name is what tells five identical
                  // checkboxes apart out of visual context.
                  aria-label={`${entry.name} no shutdown`}
                />
                {/* Named for the command, so the form teaches the CLI. */}
                <span className={cn(current.enabled ? '' : 'text-[var(--text-tertiary)]')}>
                  no shutdown
                </span>
              </label>
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="IP address">
                <Input
                  value={current.ipAddress ?? ''}
                  placeholder="192.168.1.1"
                  disabled={current.dhcp}
                  onChange={(event) =>
                    patchInterface(entry.name, { ipAddress: event.target.value || null })
                  }
                  className="h-9 font-mono text-[13px]"
                  aria-label={`${entry.name} IP address`}
                />
              </Field>
              <Field label="Subnet mask">
                <Input
                  value={current.subnetMask ?? ''}
                  placeholder="255.255.255.0"
                  disabled={current.dhcp}
                  onChange={(event) =>
                    patchInterface(entry.name, { subnetMask: event.target.value || null })
                  }
                  className="h-9 font-mono text-[13px]"
                  aria-label={`${entry.name} subnet mask`}
                />
              </Field>
            </div>

            <label className="mt-2.5 flex items-center gap-2 text-[12px]">
              <input
                type="checkbox"
                checked={current.dhcp ?? false}
                onChange={(event) =>
                  patchInterface(entry.name, {
                    dhcp: event.target.checked,
                    ipAddress: event.target.checked ? null : current.ipAddress,
                  })
                }
                className="size-3.5 accent-[var(--color-accent-500)]"
                aria-label={`${entry.name} obtain an address automatically`}
              />
              Obtain an address automatically (DHCP)
            </label>

            <div className="mt-3">
              <Field label="Description">
                <Input
                  value={current.description ?? ''}
                  placeholder="Link to core switch"
                  onChange={(event) =>
                    patchInterface(entry.name, { description: event.target.value || null })
                  }
                  className="h-9 text-[13px]"
                  aria-label={`${entry.name} description`}
                />
              </Field>
            </div>

            {isSwitchPort && spec.osiLayer <= 3 && !spec.isEndpoint && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Switchport mode">
                  <select
                    value={current.switchportMode ?? ''}
                    onChange={(event) =>
                      patchInterface(entry.name, {
                        switchportMode: (event.target.value || null) as never,
                      })
                    }
                    className={selectClass}
                    aria-label={`${entry.name} switchport mode`}
                  >
                    <option value="">Not a switch port</option>
                    <option value="access">Access</option>
                    <option value="trunk">Trunk</option>
                  </select>
                </Field>
                {current.switchportMode === 'access' && (
                  <Field label="Access VLAN">
                    <Input
                      type="number"
                      min={1}
                      max={4094}
                      value={current.accessVlan ?? ''}
                      onChange={(event) =>
                        patchInterface(entry.name, {
                          accessVlan: event.target.value ? Number(event.target.value) : null,
                        })
                      }
                      className="h-9 font-mono text-[13px]"
                      aria-label={`${entry.name} access VLAN`}
                    />
                  </Field>
                )}
              </div>
            )}

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Speed">
                <select
                  value={current.speed ?? 'auto'}
                  onChange={(event) =>
                    patchInterface(entry.name, { speed: event.target.value as never })
                  }
                  className={selectClass}
                  aria-label={`${entry.name} speed`}
                >
                  <option value="auto">Auto</option>
                  <option value="10">10 Mbps</option>
                  <option value="100">100 Mbps</option>
                  <option value="1000">1 Gbps</option>
                </select>
              </Field>
              <Field label="Duplex">
                <select
                  value={current.duplex ?? 'auto'}
                  onChange={(event) =>
                    patchInterface(entry.name, { duplex: event.target.value as never })
                  }
                  className={selectClass}
                  aria-label={`${entry.name} duplex`}
                >
                  <option value="auto">Auto</option>
                  <option value="full">Full</option>
                  <option value="half">Half</option>
                </select>
              </Field>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* General                                                                     */
/* -------------------------------------------------------------------------- */
export function GeneralForm({ config, spec, onChange }: FormProps) {
  return (
    <div className="flex flex-col gap-4">
      <Field label="Hostname" hint="Shown in the CLI prompt.">
        <Input
          value={config.hostname ?? ''}
          placeholder={spec.label.replace(/\s/g, '')}
          onChange={(event) =>
            onChange((previous) => ({ ...previous, hostname: event.target.value }))
          }
          className="h-9 text-[13px]"
          aria-label="Hostname"
        />
      </Field>

      <Field
        label="Default gateway"
        hint="Where this device sends traffic for other networks."
      >
        <Input
          value={config.defaultGateway ?? ''}
          placeholder="192.168.1.1"
          onChange={(event) =>
            onChange((previous) => ({
              ...previous,
              defaultGateway: event.target.value || null,
            }))
          }
          className="h-9 font-mono text-[13px]"
          aria-label="Default gateway"
        />
      </Field>

      <Field label="DNS servers" hint="Comma separated.">
        <Input
          value={(config.dnsServers ?? []).join(', ')}
          placeholder="8.8.8.8, 1.1.1.1"
          onChange={(event) =>
            onChange((previous) => ({
              ...previous,
              dnsServers: event.target.value
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean),
            }))
          }
          className="h-9 font-mono text-[13px]"
          aria-label="DNS servers"
        />
      </Field>

      {spec.hasCli && (
        <Field label="Enable secret" hint="Password for privileged EXEC mode.">
          <Input
            type="password"
            value={config.enableSecret ?? ''}
            onChange={(event) =>
              onChange((previous) => ({
                ...previous,
                enableSecret: event.target.value || null,
              }))
            }
            className="h-9 text-[13px]"
            aria-label="Enable secret"
          />
        </Field>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* VLANs                                                                       */
/* -------------------------------------------------------------------------- */
export function VlanForm({ config, onChange }: FormProps) {
  const vlans = config.vlans ?? [];

  const update = (index: number, changes: Partial<VlanConfig>) =>
    onChange((previous) => ({
      ...previous,
      vlans: (previous.vlans ?? []).map((vlan, position) =>
        position === index ? { ...vlan, ...changes } : vlan,
      ),
    }));

  return (
    <div className="flex flex-col gap-3">
      {vlans.length === 0 && (
        <p className="text-[13px] text-[var(--text-secondary)]">
          No VLANs yet. VLAN 1 always exists and needs no declaration.
        </p>
      )}

      {vlans.map((vlan, index) => (
        <div key={index} className="flex items-end gap-2">
          <Field label="VLAN ID">
            <Input
              type="number"
              min={1}
              max={4094}
              value={vlan.id}
              onChange={(event) => update(index, { id: Number(event.target.value) })}
              className="h-9 w-24 font-mono text-[13px]"
              aria-label={`VLAN ${index + 1} id`}
            />
          </Field>
          <Field label="Name">
            <Input
              value={vlan.name}
              placeholder="Sales"
              onChange={(event) => update(index, { name: event.target.value })}
              className="h-9 text-[13px]"
              aria-label={`VLAN ${index + 1} name`}
            />
          </Field>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Remove VLAN ${vlan.id}`}
            onClick={() =>
              onChange((previous) => ({
                ...previous,
                vlans: (previous.vlans ?? []).filter((_, position) => position !== index),
              }))
            }
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      ))}

      <Button
        variant="secondary"
        size="sm"
        leadingIcon={<Plus className="size-4" />}
        onClick={() =>
          onChange((previous) => ({
            ...previous,
            vlans: [...(previous.vlans ?? []), { id: 10, name: '' }],
          }))
        }
      >
        Add VLAN
      </Button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Routing                                                                     */
/* -------------------------------------------------------------------------- */
export function RoutingForm({ config, onChange }: FormProps) {
  const routes = config.staticRoutes ?? [];

  const update = (index: number, changes: Partial<StaticRoute>) =>
    onChange((previous) => ({
      ...previous,
      staticRoutes: (previous.staticRoutes ?? []).map((route, position) =>
        position === index ? { ...route, ...changes } : route,
      ),
    }));

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-3">
        <h4 className="text-[13px] font-semibold">Static routes</h4>

        {routes.map((route, index) => (
          <div
            key={index}
            className="rounded-[var(--radius-sm)] border border-[var(--hairline)] p-3"
          >
            <div className="grid gap-2.5 sm:grid-cols-3">
              <Field label="Network">
                <Input
                  value={route.network}
                  placeholder="0.0.0.0"
                  onChange={(event) => update(index, { network: event.target.value })}
                  className="h-9 font-mono text-[13px]"
                  aria-label={`Route ${index + 1} network`}
                />
              </Field>
              <Field label="Mask">
                <Input
                  value={route.mask}
                  placeholder="0.0.0.0"
                  onChange={(event) => update(index, { mask: event.target.value })}
                  className="h-9 font-mono text-[13px]"
                  aria-label={`Route ${index + 1} mask`}
                />
              </Field>
              <Field label="Next hop">
                <Input
                  value={route.nextHop ?? ''}
                  placeholder="203.0.113.1"
                  onChange={(event) => update(index, { nextHop: event.target.value || null })}
                  className="h-9 font-mono text-[13px]"
                  aria-label={`Route ${index + 1} next hop`}
                />
              </Field>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() =>
                onChange((previous) => ({
                  ...previous,
                  staticRoutes: (previous.staticRoutes ?? []).filter(
                    (_, position) => position !== index,
                  ),
                }))
              }
            >
              <Trash2 className="size-3.5" /> Remove
            </Button>
          </div>
        ))}

        <Button
          variant="secondary"
          size="sm"
          leadingIcon={<Plus className="size-4" />}
          onClick={() =>
            onChange((previous) => ({
              ...previous,
              staticRoutes: [
                ...(previous.staticRoutes ?? []),
                { network: '0.0.0.0', mask: '0.0.0.0', nextHop: '', distance: 1 },
              ],
            }))
          }
        >
          Add route
        </Button>
        <p className="text-[11px] text-[var(--text-tertiary)]">
          A default route is 0.0.0.0 with mask 0.0.0.0 — it matches anything the
          routing table has no better entry for.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h4 className="text-[13px] font-semibold">OSPF</h4>
        {config.ospf ? (
          <div className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Process ID">
                <Input
                  type="number"
                  value={config.ospf.processId}
                  onChange={(event) =>
                    onChange((previous) => ({
                      ...previous,
                      ospf: previous.ospf
                        ? { ...previous.ospf, processId: Number(event.target.value) }
                        : previous.ospf,
                    }))
                  }
                  className="h-9 font-mono text-[13px]"
                  aria-label="OSPF process id"
                />
              </Field>
              <Field label="Router ID">
                <Input
                  value={config.ospf.routerId ?? ''}
                  placeholder="1.1.1.1"
                  onChange={(event) =>
                    onChange((previous) => ({
                      ...previous,
                      ospf: previous.ospf
                        ? { ...previous.ospf, routerId: event.target.value || null }
                        : previous.ospf,
                    }))
                  }
                  className="h-9 font-mono text-[13px]"
                  aria-label="OSPF router id"
                />
              </Field>
            </div>

            {config.ospf.networks.map((network, index) => (
              <div key={index} className="grid gap-2.5 sm:grid-cols-3">
                <Field label="Network">
                  <Input
                    value={network.network}
                    onChange={(event) =>
                      onChange((previous) => ({
                        ...previous,
                        ospf: previous.ospf
                          ? {
                              ...previous.ospf,
                              networks: previous.ospf.networks.map((item, position) =>
                                position === index
                                  ? { ...item, network: event.target.value }
                                  : item,
                              ),
                            }
                          : previous.ospf,
                      }))
                    }
                    className="h-9 font-mono text-[13px]"
                    aria-label={`OSPF network ${index + 1}`}
                  />
                </Field>
                <Field label="Wildcard">
                  <Input
                    value={network.wildcard}
                    onChange={(event) =>
                      onChange((previous) => ({
                        ...previous,
                        ospf: previous.ospf
                          ? {
                              ...previous.ospf,
                              networks: previous.ospf.networks.map((item, position) =>
                                position === index
                                  ? { ...item, wildcard: event.target.value }
                                  : item,
                              ),
                            }
                          : previous.ospf,
                      }))
                    }
                    className="h-9 font-mono text-[13px]"
                    aria-label={`OSPF wildcard ${index + 1}`}
                  />
                </Field>
                <Field label="Area">
                  <Input
                    type="number"
                    value={network.area}
                    onChange={(event) =>
                      onChange((previous) => ({
                        ...previous,
                        ospf: previous.ospf
                          ? {
                              ...previous.ospf,
                              networks: previous.ospf.networks.map((item, position) =>
                                position === index
                                  ? { ...item, area: Number(event.target.value) }
                                  : item,
                              ),
                            }
                          : previous.ospf,
                      }))
                    }
                    className="h-9 font-mono text-[13px]"
                    aria-label={`OSPF area ${index + 1}`}
                  />
                </Field>
              </div>
            ))}

            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                leadingIcon={<Plus className="size-4" />}
                onClick={() =>
                  onChange((previous) => ({
                    ...previous,
                    ospf: previous.ospf
                      ? {
                          ...previous.ospf,
                          networks: [
                            ...previous.ospf.networks,
                            { network: '', wildcard: '0.0.0.255', area: 0 },
                          ],
                        }
                      : previous.ospf,
                  }))
                }
              >
                Add network
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onChange((previous) => ({ ...previous, ospf: null }))}
              >
                Disable OSPF
              </Button>
            </div>
            <p className="text-[11px] text-[var(--text-tertiary)]">
              OSPF takes a wildcard mask, not a subnet mask — 0.0.0.255 is the
              inverse of 255.255.255.0.
            </p>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              onChange((previous) => ({
                ...previous,
                ospf: { processId: 1, routerId: null, networks: [], passiveInterfaces: [] },
              }))
            }
          >
            Enable OSPF
          </Button>
        )}
      </section>
    </div>
  );
}
