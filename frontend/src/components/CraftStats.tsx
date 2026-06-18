import type { CraftStats, ApiModule } from "../craft";

interface Props {
  stats: CraftStats;
  hovered: ApiModule | null;
}

const CHECKS: [string, number][] = [
  ["LEO (Earth)", 9300],
  ["→ Mars transfer", 5717],
  ["→ Venus transfer", 5400],
  ["→ Jupiter transfer", 8900],
  ["→ Saturn transfer", 10500],
];

function dvColor(dv: number): string {
  if (dv > 8000) return "var(--green)";
  if (dv > 3000) return "var(--warn)";
  return "var(--alert)";
}
function twrColor(t: number): string {
  if (t > 0.5) return "var(--green)";
  if (t > 0.05) return "var(--warn)";
  return "var(--alert)";
}

export function CraftStats({ stats, hovered }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">CRAFT STATS</div>
      <div className="panel-body stats">
        <div className="stat-grid">
          <span>Total mass</span><b>{(stats.totalMass / 1000).toFixed(2)} t</b>
          <span>Dry mass</span><b>{(stats.dryMass / 1000).toFixed(2)} t</b>
          <span>Propellant</span><b>{(stats.propellant / 1000).toFixed(1)} t</b>
          <span>Stages</span><b>{stats.stages.length}</b>
          <span>Total ΔV</span>
          <b style={{ color: dvColor(stats.totalDeltaV) }}>
            {stats.totalDeltaV.toLocaleString(undefined, { maximumFractionDigits: 0 })} m/s
          </b>
          <span>Launch thrust</span><b>{(stats.launchThrust / 1000).toFixed(0)} kN</b>
          <span>Launch TWR</span>
          <b style={{ color: twrColor(stats.twr) }}>{stats.twr.toFixed(2)}</b>
          <span>Crew</span><b>{stats.crew}</b>
        </div>

        <div className="divider" />
        <div className="section-label">PER STAGE (1 = top)</div>
        {stats.stages.length === 0 && <div className="dim">No stages yet.</div>}
        {stats.stages.map((s) => (
          <div className="stage-stat" key={s.number}>
            <div className="ss-head">
              Stage {s.number}
              {s.firesFirst && <span className="dim"> · ignites first</span>}
            </div>
            <div className="ss-row">
              ΔV{" "}
              <b style={{ color: s.deltaV > 500 ? "var(--green)" : "var(--text-dim)" }}>
                {s.deltaV.toFixed(0)} m/s
              </b>
              {"  ·  "}Thr {(s.thrust / 1000).toFixed(0)} kN
              {"  ·  "}Isp {s.ispEff.toFixed(0)} s
            </div>
            <div className="ss-row dim">
              wet {(s.wetMass / 1000).toFixed(1)} t · dry {(s.dryMass / 1000).toFixed(1)} t
              {s.engines === 0 ? " · passive/payload" : ""}
            </div>
          </div>
        ))}

        <div className="divider" />
        <div className="section-label">MISSION FEASIBILITY</div>
        {CHECKS.map(([label, req]) => {
          const ok = stats.totalDeltaV >= req;
          return (
            <div key={label} className={ok ? "chk ok" : "chk no"}>
              <span>{ok ? "✓" : "✗"} {label}</span>
              <span className="dim">{req.toLocaleString()} m/s</span>
            </div>
          );
        })}

        {hovered && (
          <div className="hover-card">
            <div className="hc-name">{hovered.name}</div>
            <div className="hc-desc">{hovered.description}</div>
            <div className="hc-stats dim">
              {hovered.thrust > 0 && `Thrust ${(hovered.thrust / 1000).toFixed(0)} kN · Isp ${hovered.isp}s · `}
              {hovered.fuelCapacity > 0 && `Prop ${(hovered.fuelCapacity / 1000).toFixed(1)} t · `}
              {hovered.crew > 0 && `Crew ${hovered.crew} · `}
              Dry {hovered.dryMass} kg
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
