import { useCallback } from "react";
import { api, ApiError, type EventPayload } from "../lib/api";
import { useSim } from "../lib/simulation/store";
import type { ScenarioConfig, SimulationStatus } from "../lib/types";

/** Simulation commands (REST). Each updates local status and reports failures as toasts. */
export function useCommands() {
  const setStatus = useSim((s) => s.setStatus);
  const toast = useSim((s) => s.toast);

  const run = useCallback(async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | null> => {
    try {
      const res = await fn();
      if (res && typeof res === "object" && "running" in (res as object)) setStatus(res as unknown as SimulationStatus);
      if (ok) toast(ok, "success");
      return res;
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Backend unreachable", "error");
      return null;
    }
  }, [setStatus, toast]);

  return {
    start: () => run(api.start),
    pause: () => run(api.pause),
    toggle: () => (useSim.getState().status?.running ? run(api.pause) : run(api.start)),
    step: (ticks = 1) => run(() => api.step(ticks)),
    reset: (body: { scenario?: string; seed?: number; algorithm?: string; config?: ScenarioConfig } = {}) =>
      run(() => api.reset(body)),
    speed: (s: number) => run(() => api.setSpeed(s)),
    algorithm: (a: string, h?: string) => run(() => api.setAlgorithm(a, h)),
    inject: (payload: EventPayload, ok?: string) => run(() => api.inject(payload), ok),
  };
}
