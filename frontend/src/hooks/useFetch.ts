import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../services/api";

export interface FetchState<T> { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }

/** Runs `fn` whenever `deps` change, cancels stale requests, and exposes loading / error / reload. */
export function useFetch<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) { setLoading(false); return; }
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    fnRef.current(ctl.signal)
      .then((d) => { if (!ctl.signal.aborted) { setData(d); setLoading(false); } })
      .catch((e) => {
        if (e?.name === "AbortError") return;
        setError(e instanceof ApiError ? e : new ApiError(0, String(e?.message ?? e)));
        setLoading(false);
      });
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const id = setTimeout(() => setV(value), ms); return () => clearTimeout(id); }, [value, ms]);
  return v;
}
