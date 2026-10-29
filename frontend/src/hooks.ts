import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Load data for the current `deps`. Previous data is kept while reloading, so a
 * refetch never flashes an empty page; responses that arrive out of order are dropped.
 */
export function useAsync<T>(load: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const call = ++latest.current;
    setLoading(true);
    load().then(
      (value) => {
        if (call !== latest.current) return;
        setData(value);
        setError(undefined);
        setLoading(false);
      },
      (reason: unknown) => {
        if (call !== latest.current) return;
        setError(reason);
        setLoading(false);
      },
    );
    // `load` is recreated every render; `deps` decide when to refetch.
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

/** Call `callback` every `ms` while `active` is true. */
export function useInterval(callback: () => void, ms: number, active: boolean): void {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (!active) return undefined;
    const id = window.setInterval(() => saved.current(), ms);
    return () => window.clearInterval(id);
  }, [ms, active]);
}
