import { useEffect, useRef } from 'react';

import { learningApi } from '@/features/learning/api/learning-api';

/** How often accumulated study time is flushed to the server. */
const FLUSH_INTERVAL_MS = 60_000;

interface UseStudyTimerOptions {
  lessonId: string | null;
  enabled: boolean;
}

/**
 * Accumulates study time while a lesson is open and flushes it periodically.
 *
 * Two behaviours matter for the number to mean anything:
 *
 * * **Pauses when the tab is hidden.** Without this, a lesson left open in a
 *   background tab overnight would report eight hours of study.
 * * **Flushes on unmount**, so navigating away mid-interval does not discard
 *   the partial minute.
 *
 * Failures are swallowed: losing a minute of study time is not worth
 * interrupting a reader with an error.
 */
export function useStudyTimer({ lessonId, enabled }: UseStudyTimerOptions): void {
  const secondsRef = useRef(0);
  const lastTickRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!enabled || !lessonId) return;

    secondsRef.current = 0;
    lastTickRef.current = Date.now();

    const accumulate = () => {
      if (document.visibilityState !== 'visible') {
        // Reset the mark so hidden time is not counted when the tab returns.
        lastTickRef.current = Date.now();
        return;
      }
      const now = Date.now();
      secondsRef.current += Math.round((now - lastTickRef.current) / 1000);
      lastTickRef.current = now;
    };

    const flush = () => {
      accumulate();
      const seconds = secondsRef.current;
      if (seconds <= 0) return;
      secondsRef.current = 0;

      // The server caps this at an hour; clamp here too so a machine waking
      // from sleep does not send an obviously bogus figure that 422s.
      void learningApi
        .savePosition(lessonId, 0, Math.min(seconds, 3600))
        .catch(() => undefined);
    };

    const interval = setInterval(flush, FLUSH_INTERVAL_MS);
    document.addEventListener('visibilitychange', accumulate);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', accumulate);
      flush();
    };
  }, [lessonId, enabled]);
}
