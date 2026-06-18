import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiNode, ApiModule, Part } from "../craft";
import { computeStats } from "../craft";
import {
  getModules, saveCraft, getCrafts, updateCraft, deleteCraft,
  type CraftSummary,
} from "../api";
import { ModuleTree } from "./ModuleTree";
import { RocketStack } from "./RocketStack";
import { CraftStats } from "./CraftStats";

interface Props {
  onBack: () => void;
}

// Flatten the module tree into a name → module lookup (for loading saved crafts).
function flattenModules(nodes: ApiNode[], out: Map<string, ApiModule> = new Map()) {
  for (const n of nodes) {
    if (n.type === "module") out.set(n.name, n);
    else flattenModules(n.children, out);
  }
  return out;
}

export function CraftBuilder({ onBack }: Props) {
  const [tree, setTree] = useState<ApiNode[]>([]);
  const [parts, setParts] = useState<Part[]>([]);
  const [selectedUid, setSelectedUid] = useState<number | null>(null);
  const [hovered, setHovered] = useState<ApiModule | null>(null);
  const [name, setName] = useState("Spacecraft-1");
  const [status, setStatus] = useState<string | null>(null);
  const [crafts, setCrafts] = useState<CraftSummary[]>([]);
  const [editing, setEditing] = useState<string | null>(null); // original name being edited
  const uidRef = useRef(1);

  const moduleMap = useMemo(() => flattenModules(tree), [tree]);

  const refreshCrafts = () => getCrafts().then(setCrafts).catch(() => {});

  useEffect(() => {
    getModules().then(setTree).catch(() => setStatus("Failed to load module catalog."));
    refreshCrafts();
  }, []);

  const stats = useMemo(() => computeStats(parts), [parts]);

  const newCraft = () => {
    setParts([]); setSelectedUid(null); setEditing(null);
    setName("Spacecraft-1"); setStatus(null);
  };

  const loadCraft = (c: CraftSummary) => {
    const loaded: Part[] = [];
    const missing: string[] = [];
    for (const pn of c.partList) {
      const mod = moduleMap.get(pn);
      if (mod) loaded.push({ uid: uidRef.current++, mod });
      else missing.push(pn);
    }
    setParts(loaded);
    setName(c.name);
    setEditing(c.name);
    setSelectedUid(null);
    setStatus(missing.length
      ? `Loaded “${c.name}” (skipped unknown: ${missing.join(", ")})`
      : `Loaded “${c.name}” for editing.`);
  };

  // Add a part below the currently selected one (or at the bottom).
  const addModule = (m: ApiModule) => {
    const part: Part = { uid: uidRef.current++, mod: m };
    setParts((prev) => {
      if (selectedUid == null) return [...prev, part];
      const idx = prev.findIndex((p) => p.uid === selectedUid);
      if (idx < 0) return [...prev, part];
      const next = [...prev];
      next.splice(idx + 1, 0, part);
      return next;
    });
    setSelectedUid(part.uid);
  };

  const removePart = (uid: number) => {
    setParts((prev) => prev.filter((p) => p.uid !== uid));
    setSelectedUid(null);
  };

  const movePart = (uid: number, dir: -1 | 1) => {
    setParts((prev) => {
      const idx = prev.findIndex((p) => p.uid === uid);
      const j = idx + dir;
      if (idx < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  // Keyboard: Del removes, PgUp/PgDn reorder selected
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (selectedUid == null) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT") return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        removePart(selectedUid);
      } else if (e.key === "PageUp") {
        e.preventDefault();
        movePart(selectedUid, -1);
      } else if (e.key === "PageDown") {
        e.preventDefault();
        movePart(selectedUid, 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedUid]);

  const partNames = () => parts.map((p) => p.mod.name);

  const onSaveNew = async () => {
    if (parts.length === 0) { setStatus("Add parts before saving."); return; }
    setStatus("Saving…");
    const res = await saveCraft(name, partNames());
    if (res.error) { setStatus(`Error: ${res.error}`); return; }
    setEditing(res.name);
    setStatus(`Saved “${res.name}” — ${res.stages} stage(s), ${res.totalMassTons} t, ΔV ${res.totalDeltaV.toLocaleString()} m/s.`);
    refreshCrafts();
  };

  const onUpdate = async () => {
    if (!editing) return;
    if (parts.length === 0) { setStatus("Add parts before saving."); return; }
    setStatus("Updating…");
    const res = await updateCraft(editing, name, partNames());
    if (res.error) { setStatus(`Error: ${res.error}`); return; }
    setEditing(res.name);
    setStatus(`Updated “${res.name}” — ΔV ${res.totalDeltaV.toLocaleString()} m/s.`);
    refreshCrafts();
  };

  const onDelete = async () => {
    if (!editing) return;
    const res = await deleteCraft(editing);
    if (res.error) { setStatus(`Error: ${res.error}`); return; }
    setStatus(`Deleted “${editing}”.`);
    newCraft();
    refreshCrafts();
  };

  return (
    <div className="builder">
      <div className="builder-body">
        <ModuleTree tree={tree} onAdd={addModule} onHover={setHovered} />
        <RocketStack
          parts={parts}
          stats={stats}
          selectedUid={selectedUid}
          onSelect={setSelectedUid}
          onRemove={removePart}
          onMove={movePart}
        />
        <CraftStats stats={stats} hovered={hovered} />
      </div>

      <div className="builder-bar">
        <button className="btn back" onClick={onBack}>◄ BACK</button>

        <label className="load-field">
          Load
          <select
            value={editing ?? ""}
            onChange={(e) => {
              const c = crafts.find((x) => x.name === e.target.value);
              if (c) loadCraft(c);
            }}
          >
            <option value="">— saved craft —</option>
            {crafts.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} · ΔV {Math.round(c.totalDeltaV).toLocaleString()} · TWR {c.twr.toFixed(2)}
              </option>
            ))}
          </select>
        </label>

        <label className="name-field">
          {editing ? "Name (editing)" : "Craft name"}
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>

        <button className="btn" onClick={newCraft}>NEW</button>
        {editing && (
          <button className="btn save" onClick={onUpdate} title="Save changes to this craft">
            UPDATE
          </button>
        )}
        <button className="btn save" onClick={onSaveNew} title="Save as a new craft (unique name)">
          SAVE AS NEW
        </button>
        {editing && (
          <button className="btn danger" onClick={onDelete} title="Delete this saved craft">
            DELETE
          </button>
        )}

        <span className="builder-status">{status}</span>
        <span className="builder-hint">
          {editing
            ? `editing “${editing}” — UPDATE saves in place, SAVE AS NEW forks it`
            : "click catalog to add · select a part for ▲▼✕ · Del removes · PgUp/PgDn reorder"}
        </span>
      </div>
    </div>
  );
}
