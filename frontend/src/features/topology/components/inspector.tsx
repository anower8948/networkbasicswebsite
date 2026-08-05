/**
 * Properties panel for the current selection.
 *
 * Device configuration — addresses, VLANs, routing — is Part 5. This handles
 * only what the *designer* owns: identity, grouping, cabling and interface
 * assignment.
 */

import { Trash2, TriangleAlert } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DeviceIcon } from './device-icon';
import { deviceColor } from './device-colors';
import type { TopologyEditor } from '../hooks/use-topology-editor';
import { CABLE_LABELS, type CableKind, type DeviceSpec, type LinkIssue } from '@/types/topology';

interface InspectorProps {
  editor: TopologyEditor;
  catalog: DeviceSpec[];
  selectedDeviceId: string | null;
  selectedLinkId: string | null;
  issues: LinkIssue[];
}

const CABLE_OPTIONS: CableKind[] = [
  'straight_through',
  'crossover',
  'fiber',
  'serial',
  'console',
  'wireless',
];

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-[var(--text-secondary)]">{label}</span>
      {children}
    </div>
  );
}

function selectClass() {
  return 'glass-inset h-9 w-full rounded-[var(--radius-sm)] px-2.5 text-[13px] focus:border-accent-500 focus:outline-none';
}

function DeviceInspector({
  editor,
  catalog,
  deviceId,
}: {
  editor: TopologyEditor;
  catalog: DeviceSpec[];
  deviceId: string;
}) {
  const device = editor.document.devices.find((item) => item.id === deviceId);
  if (!device) return null;

  const spec = catalog.find((item) => item.kind === device.kind);
  const links = editor.document.links.filter(
    (link) => link.source.deviceId === deviceId || link.target.deviceId === deviceId,
  );

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center gap-3">
        <span
          className="flex size-10 items-center justify-center rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: `color-mix(in oklab, ${deviceColor(device.kind)} 16%, transparent)`,
          }}
        >
          <DeviceIcon kind={device.kind} className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-[14px] font-semibold">{spec?.label ?? device.kind}</p>
          <p className="truncate text-[12px] text-[var(--text-tertiary)]">{spec?.model}</p>
        </div>
      </div>

      <Field label="Name">
        <Input
          value={device.name}
          onChange={(event) => editor.renameDevice(deviceId, event.target.value)}
          className="h-9 text-[13px]"
          aria-label="Device name"
        />
      </Field>

      <Field label="Label">
        <Input
          value={device.label ?? ''}
          placeholder="e.g. Reception desk"
          onChange={(event) => editor.labelDevice(deviceId, event.target.value || null)}
          className="h-9 text-[13px]"
          aria-label="Device label"
        />
      </Field>

      <Field label="Group">
        <select
          value={device.groupId ?? ''}
          onChange={(event) => editor.assignToGroup(deviceId, event.target.value || null)}
          className={selectClass()}
          aria-label="Device group"
        >
          <option value="">No group</option>
          {editor.document.groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
      </Field>

      <div>
        <p className="text-[12px] font-medium text-[var(--text-secondary)]">
          Interfaces ({links.length} of {spec?.interfaces.filter((i) => i.connectable).length ?? 0}{' '}
          in use)
        </p>
        <ul className="mt-2 flex flex-col gap-1">
          {links.map((link) => {
            const isSource = link.source.deviceId === deviceId;
            const near = isSource ? link.source : link.target;
            const far = isSource ? link.target : link.source;
            const peer = editor.document.devices.find((item) => item.id === far.deviceId);

            return (
              <li
                key={link.id}
                className="flex items-center justify-between gap-2 rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] px-2.5 py-1.5 text-[12px]"
              >
                <span className="font-mono">{near.interface}</span>
                <span className="truncate text-[var(--text-tertiary)]">
                  → {peer?.name} {far.interface}
                </span>
              </li>
            );
          })}
          {links.length === 0 && (
            <li className="text-[12px] text-[var(--text-tertiary)]">Not cabled yet.</li>
          )}
        </ul>
      </div>

      <Button
        variant="danger"
        size="sm"
        leadingIcon={<Trash2 className="size-4" />}
        onClick={() => editor.removeDevice(deviceId)}
      >
        Remove device
      </Button>
    </div>
  );
}

function LinkInspector({
  editor,
  linkId,
  issues,
}: {
  editor: TopologyEditor;
  linkId: string;
  issues: LinkIssue[];
}) {
  const link = editor.document.links.find((item) => item.id === linkId);
  if (!link) return null;

  const source = editor.document.devices.find((item) => item.id === link.source.deviceId);
  const target = editor.document.devices.find((item) => item.id === link.target.deviceId);
  const warning = issues.find((issue) => issue.linkId === linkId);

  // Free ports plus the one this link already holds, so the current value is
  // always selectable.
  const sourceOptions = [
    link.source.interface,
    ...editor.freeInterfacesFor(link.source.deviceId),
  ];
  const targetOptions = [
    link.target.interface,
    ...editor.freeInterfacesFor(link.target.deviceId),
  ];

  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <p className="text-[14px] font-semibold">Cable</p>
        <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
          {source?.name} ↔ {target?.name}
        </p>
      </div>

      {warning && (
        <Alert tone="warning">
          <span className="flex items-start gap-2">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {warning.message}
          </span>
        </Alert>
      )}

      <Field label="Cable type">
        <select
          value={link.cable}
          onChange={(event) =>
            editor.updateLink(linkId, { cable: event.target.value as CableKind })
          }
          className={selectClass()}
          aria-label="Cable type"
        >
          {CABLE_OPTIONS.map((cable) => (
            <option key={cable} value={cable}>
              {CABLE_LABELS[cable]}
            </option>
          ))}
        </select>
      </Field>

      <Field label={`${source?.name ?? 'Source'} interface`}>
        <select
          value={link.source.interface}
          onChange={(event) =>
            editor.updateLink(linkId, {
              source: { ...link.source, interface: event.target.value },
            })
          }
          className={`${selectClass()} font-mono`}
          aria-label="Source interface"
        >
          {sourceOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </Field>

      <Field label={`${target?.name ?? 'Target'} interface`}>
        <select
          value={link.target.interface}
          onChange={(event) =>
            editor.updateLink(linkId, {
              target: { ...link.target, interface: event.target.value },
            })
          }
          className={`${selectClass()} font-mono`}
          aria-label="Target interface"
        >
          {targetOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </Field>

      <label className="flex items-center gap-2.5 text-[13px]">
        <input
          type="checkbox"
          checked={link.enabled}
          onChange={(event) => editor.updateLink(linkId, { enabled: event.target.checked })}
          className="size-4 accent-[var(--color-accent-500)]"
        />
        Link is up
      </label>

      <Button
        variant="danger"
        size="sm"
        leadingIcon={<Trash2 className="size-4" />}
        onClick={() => editor.removeLink(linkId)}
      >
        Remove cable
      </Button>
    </div>
  );
}

export function Inspector({
  editor,
  catalog,
  selectedDeviceId,
  selectedLinkId,
  issues,
}: InspectorProps) {
  if (selectedDeviceId) {
    return <DeviceInspector editor={editor} catalog={catalog} deviceId={selectedDeviceId} />;
  }
  if (selectedLinkId) {
    return <LinkInspector editor={editor} linkId={selectedLinkId} issues={issues} />;
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-[13px] text-[var(--text-secondary)]">
        Select a device or a cable to edit it.
      </p>

      <div className="flex flex-col gap-2">
        <p className="text-[12px] font-medium text-[var(--text-secondary)]">Groups</p>
        {editor.document.groups.map((group) => (
          <div key={group.id} className="flex items-center gap-2">
            <Input
              value={group.name}
              onChange={(event) => editor.renameGroup(group.id, event.target.value)}
              className="h-8 text-[12px]"
              aria-label={`Group name for ${group.name}`}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editor.removeGroup(group.id)}
              aria-label={`Remove group ${group.name}`}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => editor.addGroup('New area', { x: 40, y: 40 })}
        >
          Add group
        </Button>
      </div>

      {issues.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[12px] font-medium text-[var(--text-secondary)]">
            Cabling warnings ({issues.length})
          </p>
          {issues.map((issue) => (
            <p
              key={issue.linkId}
              className="rounded-[var(--radius-xs)] bg-[var(--color-warning)]/10 px-2.5 py-2 text-[12px] text-[var(--text-secondary)]"
            >
              {issue.message}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
