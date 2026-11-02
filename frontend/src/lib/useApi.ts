import { useEffect, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/** Runs `load` when `key` changes, cancelling the previous request. A null key loads nothing. */
export function useApi<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): ApiState<T> {
  const [state, setState] = useState<ApiState<T> & { key: string | null }>({
    data: null,
    error: null,
    loading: key !== null,
    key,
  });

  // Reset synchronously when the key changes, so a new slug never shows the old data.
  if (state.key !== key) {
    setState({ data: null, error: null, loading: key !== null, key });
  }

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => setState({ data, error: null, loading: false, key }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = error instanceof ApiError ? error : new ApiError("network");
        setState({ data: null, error: apiError, loading: false, key });
      },
    );
    return () => controller.abort();
    // `load` is a new closure every render; the key identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data: state.data, error: state.error, loading: state.loading };
}
