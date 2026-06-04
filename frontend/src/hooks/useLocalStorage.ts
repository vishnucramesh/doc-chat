import { useCallback, useEffect, useState } from "react";

/**
 * useState mirrored to localStorage. Reads the stored value on mount, writes
 * on every change. Falls back to the initial value if parsing fails — survives
 * a schema change without wedging the UI.
 */
export function useLocalStorage<T>(
  key: string,
  initial: T,
): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw != null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // private-browsing / quota — silently ignore. The UI keeps working.
    }
  }, [key, value]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) =>
      setValue((prev) =>
        typeof next === "function" ? (next as (p: T) => T)(prev) : next,
      ),
    [],
  );

  return [value, set];
}
