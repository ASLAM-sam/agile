/**
 * Data-fetching primitive.
 *
 * Every view that loads data gets loading, error and success states from one
 * place, so no screen can silently render only the happy path. Requests are
 * aborted on unmount and superseded by newer ones.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '@/api/client';

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
  /** True during a refetch that already has data on screen. */
  isRefreshing: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);

  // Held in a ref so the effect does not depend on the loader identity, which
  // would re-run on every render for inline arrow functions.
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const hasData = data !== null;

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    if (hasData) setIsRefreshing(true);
    else setIsLoading(true);

    loaderRef
      .current(controller.signal)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        if (caught instanceof DOMException && caught.name === 'AbortError') return;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError(0, 'unexpected_error', 'Something went wrong. Please try again.'),
        );
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
        setIsRefreshing(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { data, error, isLoading, isRefreshing, reload, setData };
}
