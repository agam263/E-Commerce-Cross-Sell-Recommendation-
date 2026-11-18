import { useCallback, useEffect, useRef, useState } from 'react'
import { describeError } from '../api/client'

/**
 * Minimal data-fetching hook: { data, error, loading, reload }.
 * `deps` controls refetching; `enabled` defers the call (e.g. until a product
 * is selected). Results from stale requests are discarded.
 */
export function useApi(fetcher, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled })
  const requestId = useRef(0)

  const run = useCallback(async () => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const id = ++requestId.current
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const data = await fetcher()
      if (id === requestId.current) setState({ data, error: null, loading: false })
    } catch (error) {
      if (id === requestId.current) {
        setState({ data: null, error: describeError(error), loading: false })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  useEffect(() => {
    run()
  }, [run])

  return { ...state, reload: run }
}

/** Debounce a fast-changing value (search boxes). */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
