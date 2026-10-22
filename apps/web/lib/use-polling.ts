"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type PollingOptions<T> = {
  /** Delay between the end of one request and the start of the next. */
  intervalMs: number;
  /** Polling stops for good after this long, even if the condition is never met. */
  maxDurationMs: number;
  /** Return true once no further updates are expected (for example a terminal status). */
  isDone: (value: T) => boolean;
  /** Consecutive failures tolerated before polling gives up. */
  maxConsecutiveErrors?: number;
};

type PollingState<T> = {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** True while more requests are scheduled. */
  polling: boolean;
  /** Set when polling stopped without reaching isDone (timeout or repeated errors). */
  gaveUp: boolean;
  refresh: () => void;
};

/**
 * Bounded, non-overlapping polling. Each request starts only after the previous one finished;
 * temporary errors back off; everything stops on unmount, when isDone is true, or when the
 * time or error budget runs out.
 */
export function usePolling<T>(fetcher: () => Promise<T>, options: PollingOptions<T>): PollingState<T> {
  const { intervalMs, maxDurationMs, maxConsecutiveErrors = 5 } = options;
  const fetcherRef = useRef(fetcher);
  const isDoneRef = useRef(options.isDone);
  useEffect(() => {
    fetcherRef.current = fetcher;
    isDoneRef.current = options.isDone;
  });

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(true);
  const [gaveUp, setGaveUp] = useState(false);
  const [generation, setGeneration] = useState(0);

  const refresh = useCallback(() => {
    setLoading(true);
    setGaveUp(false);
    setPolling(true);
    setGeneration((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();
    let failures = 0;

    async function tick() {
      try {
        const value = await fetcherRef.current();
        if (!active) return;
        failures = 0;
        setData(value);
        setError(null);
        setLoading(false);
        if (isDoneRef.current(value)) {
          setPolling(false);
          return;
        }
      } catch (reason) {
        if (!active) return;
        failures += 1;
        setError(reason);
        setLoading(false);
        if (failures >= maxConsecutiveErrors) {
          setPolling(false);
          setGaveUp(true);
          return;
        }
      }
      if (Date.now() - startedAt >= maxDurationMs) {
        setPolling(false);
        setGaveUp(true);
        return;
      }
      const delay = Math.min(intervalMs * 2 ** failures, 30_000);
      timer = setTimeout(tick, delay);
    }

    void tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [generation, intervalMs, maxDurationMs, maxConsecutiveErrors]);

  return { data, error, loading, polling, gaveUp, refresh };
}
