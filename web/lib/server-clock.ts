"use client";

import { useEffect, useState } from "react";

let offsetMs = 0;
const listeners = new Set<() => void>();

export function serverNow(): number {
  return Date.now() + offsetMs;
}

export function syncServerTime(value: string | null): void {
  if (!value) return;
  const time = /^\d+$/.test(value) ? Number(value) : Date.parse(value);
  if (!Number.isFinite(time) || time <= 0) return;
  offsetMs = time - Date.now();
  listeners.forEach((listener) => listener());
}

export function useServerNow(): number {
  const [now, setNow] = useState(serverNow);
  useEffect(() => {
    const update = () => setNow(serverNow());
    listeners.add(update);
    const timer = window.setInterval(update, 1000);
    update();
    return () => {
      listeners.delete(update);
      window.clearInterval(timer);
    };
  }, []);
  return now;
}
