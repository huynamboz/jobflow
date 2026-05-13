import { useCallback, useEffect, useState } from "react";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

/** Generic fetcher with loading + error + manual reload trigger. */
export function useDashboardSection<T>(
  fetcher: () => Promise<T>,
  refreshKey: number = 0,
): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [bump, setBump] = useState(0);

  const reload = useCallback(() => setBump((b) => b + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => alive && setData(d))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e : new Error(String(e))))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // refreshKey from parent triggers re-fetch; bump triggers internal retry
  }, [fetcher, refreshKey, bump]);

  return { data, loading, error, reload };
}
