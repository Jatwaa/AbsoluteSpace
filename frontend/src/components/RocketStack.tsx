import type { Part, CraftStats, Stage } from "../craft";
import { MODULE_COLORS, moduleKeyStat, agencyOf } from "../craft";

interface Props {
  parts: Part[];
  stats: CraftStats;
  selectedUid: number | null;
  onSelect: (uid: number) => void;
  onRemove: (uid: number) => void;
  onMove: (uid: number, dir: -1 | 1) => void;
}

export function RocketStack({ parts, stats, selectedUid, onSelect, onRemove, onMove }: Props) {
  // Map each part uid → its computed stage
  const stageOf = new Map<number, Stage>();
  stats.stages.forEach((st) => st.parts.forEach((p) => stageOf.set(p.uid, st)));

  const rows: JSX.Element[] = [];
  let lastStageNum: number | null = null;

  parts.forEach((part) => {
    const m = part.mod;
    if (m.moduleTypeId === "DECOUPLER") {
      lastStageNum = null; // force a fresh stage header after a separator
      rows.push(
        <div
          key={part.uid}
          className={`decoupler ${selectedUid === part.uid ? "sel" : ""}`}
          onClick={() => onSelect(part.uid)}
        >
          <span className="dec-label">⋯ {m.name} ⋯</span>
          {selectedUid === part.uid && (
            <span className="row-ctrls">
              <button onClick={(e) => { e.stopPropagation(); onMove(part.uid, -1); }}>▲</button>
              <button onClick={(e) => { e.stopPropagation(); onMove(part.uid, 1); }}>▼</button>
              <button className="rm" onClick={(e) => { e.stopPropagation(); onRemove(part.uid); }}>✕</button>
            </span>
          )}
        </div>
      );
      return;
    }

    const st = stageOf.get(part.uid);
    if (st && st.number !== lastStageNum) {
      lastStageNum = st.number;
      rows.push(
        <div className="stage-header" key={`stage-${st.number}-${part.uid}`}>
          <span className="stage-num">STAGE {st.number}</span>
          {st.engines > 0 ? (
            <span className="stage-dv">ΔV {st.deltaV.toFixed(0)} m/s</span>
          ) : (
            <span className="stage-dv passive">no engines · payload</span>
          )}
          {st.firesFirst && <span className="stage-tag">ignites first</span>}
        </div>
      );
    }

    const sel = selectedUid === part.uid;
    rows.push(
      <div
        key={part.uid}
        className={`part ${sel ? "sel" : ""}`}
        style={{ borderLeftColor: MODULE_COLORS[m.moduleTypeId] }}
        onClick={() => onSelect(part.uid)}
        title={m.description}
      >
        <span className="agency">{agencyOf(m.description)}</span>
        <span className="part-name">{m.name}</span>
        <span className="part-stat">{moduleKeyStat(m)}</span>
        {sel && (
          <span className="row-ctrls">
            <button onClick={(e) => { e.stopPropagation(); onMove(part.uid, -1); }}>▲</button>
            <button onClick={(e) => { e.stopPropagation(); onMove(part.uid, 1); }}>▼</button>
            <button className="rm" onClick={(e) => { e.stopPropagation(); onRemove(part.uid); }}>✕</button>
          </span>
        )}
      </div>
    );
  });

  return (
    <div className="panel">
      <div className="panel-head">
        ROCKET STACK · TOP = STAGE 1 (first part added)
      </div>
      <div className="panel-body stack">
        {parts.length === 0 ? (
          <div className="empty-hint">
            Click modules in the catalog to add them.
            <br />
            <b>The first part you add becomes Stage 1 (the top).</b>
            <br />
            Drop a <b>Stage Separator</b> between parts to start a new stage.
            <br />
            <br />
            For a <b>payload build</b>, add a command/probe core and payload
            modules — engines are optional.
          </div>
        ) : (
          rows
        )}
      </div>
    </div>
  );
}
