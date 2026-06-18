import type { ApiNode } from "./craft";

export async function getModules(): Promise<ApiNode[]> {
  const r = await fetch("/api/modules");
  const data = await r.json();
  return data.tree as ApiNode[];
}

export interface SaveCraftResult {
  name: string;
  stages: number;
  totalMassTons: number;
  totalDeltaV: number;
  crew: number;
  error?: string;
}

export async function saveCraft(
  name: string,
  parts: string[]
): Promise<SaveCraftResult> {
  const r = await fetch("/api/craft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, parts }),
  });
  return r.json();
}

export interface LaunchSite {
  id: string;
  name: string;
  short: string;
  agency: string;
  country: string;
  latitude: number;
  longitude: number;
  altitude: number;
  climate: string;
  pads: string[];
  maxWindSurface: number;
}

export async function getLaunchSites(): Promise<LaunchSite[]> {
  const r = await fetch("/api/launch-sites");
  return (await r.json()).sites as LaunchSite[];
}

export interface WindowOption {
  departDate: string;
  arriveDate: string;
  departTime: number;
  durationDays: number;
  dvTotal: number;
  quality: string;
}

export async function getWindows(
  origin: string,
  dest: string
): Promise<WindowOption[]> {
  const r = await fetch(`/api/windows?origin=${origin}&dest=${dest}`);
  return (await r.json()).windows as WindowOption[];
}
