import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiNode, ApiModule, Part } from "../craft";
import { computeStats } from "../craft";
import { getModules, saveCraft } from "../api";
import { ModuleTree } from "./ModuleTree";
import { RocketStack } from "./RocketStack";
import { CraftStats } from "./CraftStats";

interface Props {
  onBack: () => void;
}

export function CraftBuilder({ onBack }: Props) {
  const [tree, setTree] = useState<ApiNode[]>([]);
  const [parts, setParts] = useState<Part[]>([]);
  const [selectedUid, setSelectedUid] = useState<number | null>(null);
  const [hovered, setHovered] = useState<ApiModule | null>(null);
  const [name, setName] = useState("Spacecraft-1");
  const [status, setStatus] = useState<string | null>(null);
  const uidRef = useRef(1);

  useEffect(() => {
    getModules().then(setTree).catch(() => setStatus("Failed to load module catalog."));
  }, []);

  const stats = useMemo(() => computeStats(parts), [parts]);

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

  const onSave = async () => {
    if (parts.length === 0) {
      setStatus("Add parts before saving.");
      return;
    }
    setStatus("Saving…");
    const res = await saveCraft(name, parts.map((p) => p.mod.name));
    if (res.error) setStatus(`Error: ${res.error}`);
    else
      setStatus(
        `Saved “${res.name}” — ${res.stages} stage(s), ${res.totalMassTons} t, ΔV ${res.totalDeltaV.toLocaleString()} m/s.`
      );
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
        <label className="name-field">
          Craft name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="btn" onClick={() => { setParts([]); setSelectedUid(null); setStatus(null); }}>
          RESET
        </button>
        <button className="btn save" onClick={onSave}>SAVE CRAFT</button>
        <span className="builder-status">{status}</span>
        <span className="builder-hint">
          click catalog to add · select a part for ▲▼✕ · Del removes · PgUp/PgDn reorder
        </span>
      </div>
    </div>
  );
}
