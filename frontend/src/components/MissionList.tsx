import type { Mission } from "../types";

interface Props {
  missions: Mission[];
  critical: number;
  selected: string | null;
  onSelect: (name: string) => void;
}

const urgencyRank: Record<string, number> = {
  CRITICAL: 0,
  SOON: 1,
  UPCOMING: 2,
  NOMINAL: 3,
  NONE: 4,
};

export function MissionList({ missions, critical, selected, onSelect }: Props) {
  const sorted = [...missions].sort((a, b) => {
    const ru = urgencyRank[a.attention.urgency] - urgencyRank[b.attention.urgency];
    if (ru !== 0) return ru;
    return (a.attention.time ?? Infinity) - (b.attention.time ?? Infinity);
  });

  return (
    <div className="panel">
      <div className="panel-head">ACTIVE MISSIONS · FLEET STATUS</div>
      <div className="panel-body">
        <div className="fleet-summary">
          <span className="dim">Fleet: {missions.length} craft</span>
          {critical > 0 ? (
            <span className="crit">⚠ {critical} REQUIRE ATTENTION</span>
          ) : (
            <span className="ok">✓ All nominal</span>
          )}
        </div>

        {sorted.length === 0 ? (
          <div className="empty-hint">
            No active missions.
            <br />
            Open <b>VEHICLE ASSEMBLY</b> to design and launch a craft.
          </div>
        ) : (
          sorted.map((m) => {
            const u = m.attention.urgency;
            const sel = m.name === selected;
            return (
              <div
                key={m.name}
                className={`mission-row b-${u} ${sel ? "selected" : ""}`}
                onClick={() => onSelect(m.name)}
              >
                <div className="name">{m.name}</div>
                <div className="route">
                  {m.origin.slice(0, 5)} → {m.destination.slice(0, 7)}
                </div>
                <div className="phase">{m.phase}</div>
                <div className={`next u-${u}`}>{m.attention.countdown}</div>
                <div className="detail">
                  {m.crew > 0 ? `${m.crew} crew` : "uncrewed"} · ΔV{" "}
                  {m.deltaV.toLocaleString()} m/s · fuel {m.fuelTons} t
                </div>
                <div className={`attn u-${u}`}>
                  {u === "CRITICAL" ? "⚠ " : "→ "}
                  {m.attention.label}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
