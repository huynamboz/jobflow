import { useCallback, useEffect, useRef, useState } from "react";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

/** Generic fetcher with loading + error + manual reload trigger.
 *
 * Important: ``fetcher`` is intentionally NOT in the effect's dependency
 * array — every parent render creates a new arrow function, which would
 * re-trigger the effect on every render and cause an infinite re-fetch
 * loop. We pin the latest fetcher in a ref so the effect always calls
 * the freshest implementation while only re-running on ``refreshKey`` or
 * internal ``bump`` (from ``reload()``).
 */
export function useDashboardSection<T>(
  fetcher: () => Promise<T>,
  refreshKey: number = 0,
): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [bump, setBump] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(() => setBump((b) => b + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetcherRef.current()
      .then((d) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, bump]);

  return { data, loading, error, reload };
}
