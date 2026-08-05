import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { usePacketAnimation } from './use-packet-animation';
import type { SimulationResult, TraceEvent } from '@/types/simulation';

function event(step: number, overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    step,
    kind: 'forward',
    deviceId: 'pc1',
    deviceName: 'PC1',
    interface: 'Ethernet0',
    linkId: 'l1',
    toDeviceId: 'sw1',
    toInterface: 'FastEthernet0/1',
    summary: `step ${step}`,
    detail: null,
    frame: null,
    ok: true,
    ...overrides,
  };
}

const result: SimulationResult = {
  success: true,
  protocol: 'ICMP',
  summary: 'Reply received',
  failureReason: null,
  hint: null,
  events: [
    event(1, { kind: 'note', linkId: null }),
    event(2),
    event(3, { linkId: 'l2', deviceId: 'r1', deviceName: 'R1' }),
  ],
};

describe('usePacketAnimation', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('starts before the first step', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(null));

    expect(hook.current.currentStep).toBe(-1);
    expect(hook.current.currentEvent).toBeNull();
    expect(hook.current.isPlaying).toBe(false);
  });

  it('plays automatically when a result arrives', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));
    expect(hook.current.isPlaying).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(hook.current.currentStep).toBe(0);
  });

  it('advances through every step and then stops', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));

    // Each tick is scheduled by an effect that re-runs after the state update,
    // so time has to advance once per step rather than in one jump.
    for (let tick = 0; tick <= result.events.length; tick += 1) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }

    expect(hook.current.currentStep).toBe(result.events.length - 1);
    expect(hook.current.isPlaying).toBe(false);
  });

  it('exposes the active link only when the step crosses a cable', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));

    // Step 0 is a note with no link — nothing to animate.
    act(() => hook.current.seek(0));
    expect(hook.current.activeLinkId).toBeNull();

    act(() => hook.current.seek(1));
    expect(hook.current.activeLinkId).toBe('l1');
  });

  it('reports the direction so the canvas animates the right way', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));

    act(() => hook.current.seek(2));

    expect(hook.current.activeDirection).toEqual({ from: 'r1', to: 'sw1' });
  });

  it('steps forward and back without playing', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));
    act(() => hook.current.pause());

    act(() => hook.current.stepForward());
    expect(hook.current.currentStep).toBe(0);

    act(() => hook.current.stepForward());
    expect(hook.current.currentStep).toBe(1);

    act(() => hook.current.stepBack());
    expect(hook.current.currentStep).toBe(0);
    expect(hook.current.isPlaying).toBe(false);
  });

  it('does not step past the end', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));
    act(() => hook.current.seek(result.events.length - 1));

    act(() => hook.current.stepForward());

    expect(hook.current.currentStep).toBe(result.events.length - 1);
  });

  it('restarts from the beginning when played after finishing', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));
    act(() => hook.current.seek(result.events.length - 1));

    act(() => hook.current.play());

    expect(hook.current.currentStep).toBe(-1);
    expect(hook.current.isPlaying).toBe(true);
  });

  it('resets to the start', () => {
    const { result: hook } = renderHook(() => usePacketAnimation(result));
    act(() => hook.current.seek(2));

    act(() => hook.current.reset());

    expect(hook.current.currentStep).toBe(-1);
    expect(hook.current.isPlaying).toBe(false);
  });
});
