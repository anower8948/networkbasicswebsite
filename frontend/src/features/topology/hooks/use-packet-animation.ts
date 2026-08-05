/**
 * Drives packet animation along the topology's links.
 *
 * The simulation returns an ordered trace; every event carrying a `linkId`
 * represents traffic crossing a cable. This walks those in order, exposing the
 * currently-animating step so the canvas can draw a packet on that edge.
 *
 * Playback is *stepped*, not time-interpolated: a learner reads the trace line
 * that matches what they are watching, and a continuous animation would drift
 * out of step with the list.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { SimulationResult, TraceEvent } from '@/types/simulation';

/** Milliseconds each animated hop is shown. */
const STEP_MS = 900;

export interface PacketAnimation {
  /** Index into `events`, or -1 when nothing is playing. */
  currentStep: number;
  currentEvent: TraceEvent | null;
  /** The link a packet is crossing right now, if any. */
  activeLinkId: string | null;
  /** Direction along that link, so the canvas animates the right way. */
  activeDirection: { from: string; to: string | null } | null;

  isPlaying: boolean;
  play: () => void;
  pause: () => void;
  reset: () => void;
  stepForward: () => void;
  stepBack: () => void;
  seek: (index: number) => void;
}

export function usePacketAnimation(result: SimulationResult | null): PacketAnimation {
  const events = useMemo(() => result?.events ?? [], [result]);
  const [currentStep, setCurrentStep] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const timer = useRef<number | null>(null);

  // A new result restarts playback from the beginning.
  useEffect(() => {
    setCurrentStep(-1);
    setIsPlaying(Boolean(result));
  }, [result]);

  useEffect(() => {
    if (!isPlaying) return;

    timer.current = window.setTimeout(() => {
      setCurrentStep((step) => {
        if (step + 1 >= events.length) {
          setIsPlaying(false);
          return step;
        }
        return step + 1;
      });
    }, STEP_MS);

    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [isPlaying, currentStep, events.length]);

  const currentEvent = currentStep >= 0 ? (events[currentStep] ?? null) : null;

  const play = useCallback(() => {
    // Replaying from the end restarts rather than doing nothing.
    setCurrentStep((step) => (step + 1 >= events.length ? -1 : step));
    setIsPlaying(true);
  }, [events.length]);

  const pause = useCallback(() => setIsPlaying(false), []);

  const reset = useCallback(() => {
    setIsPlaying(false);
    setCurrentStep(-1);
  }, []);

  const stepForward = useCallback(() => {
    setIsPlaying(false);
    setCurrentStep((step) => Math.min(step + 1, events.length - 1));
  }, [events.length]);

  const stepBack = useCallback(() => {
    setIsPlaying(false);
    setCurrentStep((step) => Math.max(step - 1, -1));
  }, []);

  const seek = useCallback((index: number) => {
    setIsPlaying(false);
    setCurrentStep(index);
  }, []);

  return {
    currentStep,
    currentEvent,
    activeLinkId: currentEvent?.linkId ?? null,
    activeDirection: currentEvent?.linkId
      ? { from: currentEvent.deviceId, to: currentEvent.toDeviceId }
      : null,
    isPlaying,
    play,
    pause,
    reset,
    stepForward,
    stepBack,
    seek,
  };
}
