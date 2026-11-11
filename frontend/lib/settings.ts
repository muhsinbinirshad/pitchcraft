"use client";

import { useCallback, useSyncExternalStore } from "react";

export interface Settings {
  apiKey: string;
  model: string;
  effort: "low" | "medium" | "high" | "xhigh" | "max";
  review: boolean;
  visual: boolean;
  autoApply: boolean;
}

const KEY = "pitchcraft.settings";
export const DEFAULT_SETTINGS: Settings = {
  apiKey: "", model: "claude-opus-5-5", effort: "high", review: true, visual: false, autoApply: false,
};

let cache: Settings | null = null;
const listeners = new Set<() => void>();

function read(): Settings {
  if (cache) return cache;
  try {
    cache = { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    cache = { ...DEFAULT_SETTINGS };
  }
  return cache!;
}

export function getSettings(): Settings {
  return typeof window === "undefined" ? DEFAULT_SETTINGS : read();
}

export function setSettings(patch: Partial<Settings>) {
  cache = { ...read(), ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    /* private mode: keep in memory only */
  }
  listeners.forEach((l) => l());
}

export function useSettings(): [Settings, (p: Partial<Settings>) => void] {
  const s = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    read,
    () => DEFAULT_SETTINGS,
  );
  return [s, useCallback(setSettings, [])];
}
