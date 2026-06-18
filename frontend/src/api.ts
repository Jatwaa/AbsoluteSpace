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

export interface CraftSummary {
  name: string;
  stages: number;
  totalMassTons: number;
  totalDeltaV: number;
  twr: number;
  crew: number;
  partNames: string[];
  partList: string[]; // full ordered parts incl. decouplers — for loading
}

export async function getCrafts(): Promise<CraftSummary[]> {
  const r = await fetch("/api/crafts");
  return (await r.json()).crafts as CraftSummary[];
}

export async function updateCraft(
  originalName: string,
  name: string,
  parts: string[]
): Promise<SaveCraftResult> {
  const r = await fetch("/api/craft/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ originalName, name, parts }),
  });
  return r.json();
}

export async function deleteCraft(name: string): Promise<{ ok?: boolean; error?: string }> {
  const r = await fetch("/api/craft/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
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
