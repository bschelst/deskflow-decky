// Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

/**
 * Shared status state.
 *
 * One subscription to the backend's `deskflow_state` event, so the panel and the
 * settings page can never disagree about what the helper is doing.
 *
 * The backend pushes; the poll below is only a safety net for a missed event, and it
 * runs solely while the Quick Access Menu is visible.
 */

import { addEventListener, removeEventListener, useQuickAccessVisible } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";

import { getStatus } from "../api/backend";
import { toStatus } from "../api/guards";
import type { BackendError, Status } from "../api/types";

const SAFETY_POLL_MS = 5000;

export interface StatusView {
  status: Status | null;
  error: BackendError | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useDeskflowStatus(): StatusView {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<BackendError | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    const result = await getStatus();
    if (!mounted.current) return;
    if (result.ok) {
      setStatus(result.data);
      setError(null);
    } else {
      setError(result.error);
    }
    setLoading(false);
  }, []);

  const visible = useQuickAccessVisible();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    // The event payload is the same shape get_status returns, and is just as
    // untrusted: it goes through the same guard.
    const onState = (payload: unknown) => {
      const next = toStatus(payload);
      if (next && mounted.current) {
        setStatus(next);
        setError(null);
        setLoading(false);
      }
    };

    addEventListener<[unknown]>("deskflow_state", onState);
    return () => removeEventListener<[unknown]>("deskflow_state", onState);
  }, []);

  useEffect(() => {
    if (!visible) return undefined;
    void refresh();
    const timer = setInterval(() => void refresh(), SAFETY_POLL_MS);
    return () => clearInterval(timer);
  }, [visible, refresh]);

  return { status, error, loading, refresh };
}

/**
 * Guarantees a button cannot be double-submitted and that a rejected call still
 * clears the busy flag.
 */
export function useAction(
  refresh: () => Promise<void>,
): [boolean, (run: () => Promise<{ ok: boolean; error?: BackendError }>) => Promise<void>, BackendError | null] {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<BackendError | null>(null);

  const perform = useCallback(
    async (run: () => Promise<{ ok: boolean; error?: BackendError }>) => {
      if (busy) return;
      setBusy(true);
      try {
        const result = await run();
        setActionError(result.ok ? null : (result.error ?? null));
      } finally {
        // Refresh first, then re-enable. Clearing `busy` before the status has caught
        // up leaves a window where a second press acts on stale displayed state.
        try {
          await refresh();
        } finally {
          setBusy(false);
        }
      }
    },
    [busy, refresh],
  );

  return [busy, perform, actionError];
}
