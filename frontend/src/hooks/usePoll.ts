import { useEffect, useRef, useState } from "react";

/** Fetch on mount / dependency change, then refresh every `interval` ms while mounted. */
export function usePoll<T>(fn: () => Promise<T>, deps: unknown[], interval = 1500) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    let timer = 0;
    setData(null);
    const tick = async () => {
      try {
        const d = await fnRef.current();
        if (alive) { setData(d); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "request failed");
      }
      if (alive && interval > 0) timer = window.setTimeout(tick, interval);
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, setData };
}
