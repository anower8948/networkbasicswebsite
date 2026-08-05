/**
 * A Cisco-style console.
 *
 * Deliberately a plain scrolling `<div>` with a hidden input rather than a
 * terminal emulator library: there is no cursor addressing, no colour escapes
 * and no PTY here — just lines in and lines out — so a 200 kB emulator would
 * buy nothing.
 *
 * Command history (up/down) and tab completion are included because their
 * absence is the first thing anyone who has used IOS notices.
 */

import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';

import { deviceApi } from '../api/device-api';
import { cn } from '@/lib/cn';
import { ApiError } from '@/lib/api-client';
import {
  initialSession,
  type CliSession,
  type DeviceConfig,
} from '@/types/device-config';
import type { TopologyDocument } from '@/types/topology';

/** Commands offered by tab completion, by mode. */
const COMPLETIONS: Record<string, string[]> = {
  user_exec: ['enable', 'exit', 'ping', 'show'],
  priv_exec: [
    'configure terminal',
    'disable',
    'copy running-config startup-config',
    'show running-config',
    'show ip interface brief',
    'show ip route',
    'show vlan brief',
    'show version',
    'ping',
    'exit',
  ],
  global_config: [
    'hostname',
    'interface',
    'vlan',
    'ip route',
    'ip default-gateway',
    'ip dhcp pool',
    'ip name-server',
    'router ospf',
    'router eigrp',
    'router rip',
    'access-list',
    'enable secret',
    'banner motd',
    'exit',
    'end',
  ],
  interface_config: [
    'ip address',
    'no shutdown',
    'shutdown',
    'description',
    'switchport mode access',
    'switchport mode trunk',
    'switchport access vlan',
    'ip nat inside',
    'ip nat outside',
    'ip access-group',
    'speed',
    'duplex',
    'exit',
    'end',
  ],
  vlan_config: ['name', 'exit', 'end'],
  router_config: ['network', 'router-id', 'passive-interface', 'no auto-summary', 'exit', 'end'],
  dhcp_config: ['network', 'default-router', 'dns-server', 'domain-name', 'exit', 'end'],
  line_config: ['password', 'login', 'exit', 'end'],
};

interface HistoryLine {
  text: string;
  kind: 'command' | 'output' | 'system';
}

interface CliTerminalProps {
  document: TopologyDocument;
  deviceId: string;
  deviceName: string;
  config: DeviceConfig;
  onConfigChange: (config: DeviceConfig) => void;
}

export function CliTerminal({
  document: topology,
  deviceId,
  deviceName,
  config,
  onConfigChange,
}: CliTerminalProps) {
  const [session, setSession] = useState<CliSession>(() =>
    initialSession(config.hostname || deviceName),
  );
  const [lines, setLines] = useState<HistoryLine[]>([
    { text: 'Connected via console. Press Enter to begin.', kind: 'system' },
    { text: '', kind: 'output' },
  ]);
  const [input, setInput] = useState('');
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const prompt = session.hostname
    ? `${session.hostname}${promptSuffix(session.mode)}`
    : `${deviceName}>`;

  const run = useMutation({
    mutationFn: (command: string) =>
      deviceApi.runCommand(topology, deviceId, command, session, config),
    onSuccess: (result) => {
      setSession(result.session);
      if (result.changed) onConfigChange(result.config);
      if (result.output) {
        setLines((current) => [
          ...current,
          ...result.output.replace(/\n$/, '').split('\n').map((text) => ({
            text,
            kind: 'output' as const,
          })),
        ]);
      }
    },
    onError: (error) => {
      setLines((current) => [
        ...current,
        {
          text:
            error instanceof ApiError
              ? `% ${error.message}`
              : '% Could not reach the device.',
          kind: 'system',
        },
      ]);
    },
  });

  // Keep the newest line in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines]);

  const submit = () => {
    const command = input;
    setLines((current) => [...current, { text: `${prompt}${command}`, kind: 'command' }]);
    setInput('');
    setHistoryIndex(-1);

    if (command.trim()) {
      setCommandHistory((current) => [...current, command]);
      run.mutate(command);
    }
  };

  const complete = () => {
    const candidates = COMPLETIONS[session.mode] ?? [];
    const typed = input.toLowerCase();
    const hits = candidates.filter((item) => item.toLowerCase().startsWith(typed));

    if (hits.length === 1) {
      setInput(hits[0] + ' ');
    } else if (hits.length > 1 && typed) {
      // IOS prints the candidates rather than guessing.
      setLines((current) => [
        ...current,
        { text: `${prompt}${input}`, kind: 'command' },
        { text: hits.join('  '), kind: 'output' },
      ]);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      submit();
      return;
    }
    if (event.key === 'Tab') {
      event.preventDefault();
      complete();
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      const next = historyIndex < 0 ? commandHistory.length - 1 : historyIndex - 1;
      if (next >= 0) {
        setHistoryIndex(next);
        setInput(commandHistory[next] ?? '');
      }
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (historyIndex < 0) return;
      const next = historyIndex + 1;
      if (next >= commandHistory.length) {
        setHistoryIndex(-1);
        setInput('');
      } else {
        setHistoryIndex(next);
        setInput(commandHistory[next] ?? '');
      }
      return;
    }
    // Ctrl-Z leaves configuration mode, as `end` does.
    if (event.key === 'z' && event.ctrlKey) {
      event.preventDefault();
      setInput('end');
    }
  };

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-[var(--radius-md)] bg-[oklch(0.16_0.012_265)]"
      onClick={() => inputRef.current?.focus()}
      role="presentation"
    >
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-[12.5px] leading-[1.55]"
        aria-live="polite"
        aria-label="Console output"
      >
        {lines.map((line, index) => (
          <div
            key={index}
            className={cn(
              'whitespace-pre-wrap break-words',
              line.kind === 'command' && 'text-[oklch(0.92_0.02_150)]',
              line.kind === 'output' && 'text-[oklch(0.82_0.01_250)]',
              line.kind === 'system' && 'text-[oklch(0.62_0.10_250)] italic',
            )}
          >
            {line.text || ' '}
          </div>
        ))}

        {/* The live prompt sits inline with the scrollback, as a real console. */}
        <div className="flex items-baseline">
          <span className="shrink-0 text-[oklch(0.92_0.02_150)]">{prompt}</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            disabled={run.isPending}
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            aria-label="Console input"
            className="min-w-0 flex-1 bg-transparent font-mono text-[12.5px] text-[oklch(0.95_0_0)] caret-[oklch(0.7_0.17_150)] outline-none"
          />
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-white/10 px-3 py-1.5 text-[11px] text-[oklch(0.6_0.02_250)]">
        <span>Tab completes · ↑↓ history · Ctrl-Z ends config mode</span>
        <span className="font-mono">{session.mode.replace(/_/g, ' ')}</span>
      </div>
    </div>
  );
}

function promptSuffix(mode: CliSession['mode']): string {
  switch (mode) {
    case 'user_exec':
      return '>';
    case 'priv_exec':
      return '#';
    case 'global_config':
      return '(config)#';
    case 'interface_config':
      return '(config-if)#';
    case 'vlan_config':
      return '(config-vlan)#';
    case 'router_config':
      return '(config-router)#';
    case 'line_config':
      return '(config-line)#';
    case 'dhcp_config':
      return '(dhcp-config)#';
  }
}
