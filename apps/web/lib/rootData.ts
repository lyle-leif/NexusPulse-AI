import { useSyncExternalStore } from "react";

/*
 * Values kept as <html> data attributes (theme, intro seen). The layout's inline script sets them
 * before first paint; components read them here and change them with setRootData, which re-renders
 * every reader at once.
 */
const listeners = new Set<() => void>();

export function setRootData(key: string, value: string | undefined) {
  const ds = document.documentElement.dataset;
  if (value === undefined) delete ds[key];
  else ds[key] = value;
  listeners.forEach((l) => l());
}

export function useRootData<T>(read: () => T, serverValue: T): T {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    read,
    () => serverValue,
  );
}
