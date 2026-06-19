import { useEffect, useState } from "react";
import { windTunnel, type WindTunnelResult } from "../api";
import { MODULE_COLORS } from "../craft";

interface Props {
  parts: string[];     // ordered module names (nose → tail)
  craftName: string;
  onClose: () => void;
}

const VERDICT_CLASS: Record<string, string> = {
  "FLIGHT-WORTHY": "wt-good",
  "MARGINAL": "wt-warn",
  "NOT FLIGHT-WORTHY": "wt-bad",
};

export function WindTunnel({ parts, craftName, onClose }: Props) {
  const [res, setRes] = useState<WindTunnelResult | null>(null);
  const [loading, setLoading] = useState(true);

  const run = () => {
    setLoading(true);
    windTunnel(parts, craftName)
      .then((r) => setRes(r))
      .catch(() => setRes(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { run(); /* eslint-disable-next-line */ }, []);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="wt-modal" onClick={(e) => e.stopPropagation()}>
        <div className="wt-head">
          <span>VIRTUAL WIND TUNNEL · {craftName}</span>
          <div>
            <button className="btn sm" onClick={run}>↻ Re-run</button>
            <button className="dir-x" onClick={onClose}>✕</button>
          </div>
        </div>

        {loading && <div className="wt-loading">Running aerodynamic assessment…</div>}
        {res?.error && <div className="wt-loading wt-bad">Error: {res.error}</div>}

        {res && !res.error && (
          <div className="wt-body">
            <Silhouette res={res} />

            <div className="wt-readout">
              <div className={`wt-verdict ${VERDICT_CLASS[res.verdict]}`}>{res.verdict}</div>

              <div className="wt-metrics">
                <Metric label="Stability"
                  value={res.stability}
                  cls={res.stability === "STABLE" ? "wt-good" : res.stability === "MARGINAL" ? "wt-warn" : "wt-bad"} />
                <Metric label="Static margin" value={`${res.staticMarginCal.toFixed(2)} cal`} />
                <Metric label="Fineness ratio" value={`${res.finenessRatio.toFixed(1)} : 1`} />
                <Metric label="Liftoff TWR" value={res.twr.toFixed(2)}
                  cls={res.twr < 1 ? "wt-bad" : res.twr < 1.2 ? "wt-warn" : "wt-good"} />
                <Metric label="Max-Q" value={res.maxQLevel}
                  cls={res.maxQLevel === "SEVERE" ? "wt-bad" : res.maxQLevel === "HIGH" ? "wt-warn" : "wt-good"} />
                <Metric label="Control authority" value={res.controlAuthority}
                  cls={res.controlAuthority === "OK" ? "wt-good" : res.controlAuthority === "LIMITED" ? "wt-warn" : "wt-bad"} />
                <Metric label="Body" value={`${res.length.toFixed(0)} m × ⌀${res.diameter.toFixed(1)} m`} />
                <Metric label="Ballistic coef" value={res.ballisticCoef.toLocaleString()} />
              </div>

              <div className="wt-section-label">FLIGHT-CHARACTERISTIC ISSUES</div>
              {res.issues.length === 0 ? (
                <div className="wt-clean">✓ No adverse flight characteristics detected.</div>
              ) : (
                res.issues.map((i) => (
                  <div key={i.code} className={`wt-issue sev-${i.severity}`}>
                    <div className="wt-issue-head">
                      <span className="wt-sev">{i.severity}</span>
                      <span className="wt-issue-title">{i.title}</span>
                    </div>
                    <div className="wt-issue-detail">{i.detail}</div>
                  </div>
                ))
              )}

              {res.flightEvents.length > 0 && (
                <>
                  <div className="wt-section-label">POTENTIAL IN-FLIGHT EVENTS (rolled at launch)</div>
                  {res.flightEvents.map((e) => (
                    <div key={e.code} className="wt-event">
                      <span className="wt-event-chance">{Math.round(e.chance * 100)}%</span>
                      <span>{e.description}</span>
                    </div>
                  ))}
                </>
              )}

              <div className="wt-note">
                Issues are noted only — adjust the design (mass placement, engines,
                tankage, length) to improve flight characteristics. This profile drives
                the events simulated during launch.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="wt-metric">
      <span className="wt-m-label">{label}</span>
      <span className={`wt-m-value ${cls ?? ""}`}>{value}</span>
    </div>
  );
}

function Silhouette({ res }: { res: WindTunnelResult }) {
  const W = 150, H = 420, PAD = 30;
  const drawH = H - PAD * 2;
  const maxW = Math.max(res.diameter, 0.1);
  const cx = W / 2;

  return (
    <svg className="wt-svg" viewBox={`0 0 ${W} ${H}`}>
      {/* axis */}
      <line x1={cx} y1={PAD - 8} x2={cx} y2={H - PAD + 8} stroke="var(--grid)" strokeDasharray="2 3" />

      {/* parts (nose at top) */}
      {res.profile.map((p, i) => {
        const h = Math.max(3, (p.length / Math.max(res.length, 0.1)) * drawH);
        const w = Math.max(6, (p.width / maxW) * (W - 40));
        const yc = PAD + p.posFrac * drawH;
        const color = MODULE_COLORS[p.type] ?? "#555";
        return (
          <rect key={i} x={cx - w / 2} y={yc - h / 2} width={w} height={h}
            rx={p.type === "COMMAND" || p.type === "PAYLOAD" ? Math.min(w / 2, 8) : 2}
            fill={color} stroke="#0008" strokeWidth="0.5">
            <title>{p.name}</title>
          </rect>
        );
      })}

      {/* CoP (orange) and CoM (blue) markers */}
      {(() => {
        const yCoP = PAD + res.copFraction * drawH;
        const yCoM = PAD + res.comFraction * drawH;
        return (
          <>
            <line x1={6} y1={yCoP} x2={W - 6} y2={yCoP} stroke="var(--orange)" strokeWidth="1.5" />
            <text x={8} y={yCoP - 3} fill="var(--orange)" fontSize="9">CoP</text>
            <line x1={6} y1={yCoM} x2={W - 6} y2={yCoM} stroke="var(--accent)" strokeWidth="1.5" />
            <text x={W - 26} y={yCoM - 3} fill="var(--accent)" fontSize="9">CoM</text>
          </>
        );
      })()}

      <text x={cx} y={14} fill="var(--text-dim)" fontSize="9" textAnchor="middle">nose</text>
      <text x={cx} y={H - 6} fill="var(--text-dim)" fontSize="9" textAnchor="middle">tail</text>
    </svg>
  );
}
