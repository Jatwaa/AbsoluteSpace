import type { GameConnection } from "../useGameSocket";
import type { LaunchSequenceState } from "../types";

interface Props {
  seq: LaunchSequenceState;
  conn: GameConnection;
}

const PHASES = ["IGNITION", "ASCENT", "MAXQ", "STAGING", "UPPER", "INSERTION"];
const MAX_ALT = 200; // km, for the gauge

export function LaunchSequenceView({ seq, conn }: Props) {
  const t = seq.telemetry;
  const decision = seq.status === "DECISION" ? seq.decision : null;
  const done = seq.status === "DONE";

  return (
    <div className="ls-overlay">
      <div className="ls-frame">
        {/* Header */}
        <div className="ls-header">
          <div>
            <div className="ls-title">LAUNCH · {seq.title}</div>
            <div className="ls-sub">{seq.craftName} · {seq.crewLabel}{seq.crewed ? " · CREWED" : " · uncrewed"}</div>
          </div>
          <div className="ls-phase-now">
            <div className="ls-phase-title">{seq.phaseTitle}</div>
            <div className="ls-layer">{seq.layer}</div>
          </div>
        </div>

        {/* Phase timeline */}
        <div className="ls-timeline">
          {PHASES.map((p, i) => {
            const state = i < seq.phaseIndex ? "done"
              : i === seq.phaseIndex ? "active" : "future";
            return (
              <div key={p} className={`ls-phase ${state}`}>
                <div className="ls-phase-bar">
                  {i === seq.phaseIndex && (
                    <div className="ls-phase-fill" style={{ width: `${seq.phaseProgress * 100}%` }} />
                  )}
                </div>
                <span>{p}</span>
              </div>
            );
          })}
        </div>

        <div className="ls-main">
          {/* Ascent gauge */}
          <div className="ls-ascent">
            <AscentGauge altitudeKm={t.altitudeKm} />
          </div>

          {/* Telemetry + comm */}
          <div className="ls-right">
            <div className="ls-telemetry">
              <Tele label="ALTITUDE" value={`${t.altitudeKm.toFixed(1)} km`} />
              <Tele label="VELOCITY" value={`${t.velocityKms.toFixed(2)} km/s`} />
              <Tele label="DYN. PRESSURE" value={`${t.qKpa.toFixed(1)} kPa`}
                warn={t.qKpa > 30} />
              <Tele label="THROTTLE" value={`${Math.round(t.throttle * 100)}%`}
                warn={t.throttle < 1} />
            </div>

            <div className="ls-comm">
              <div className="ls-comm-head">FLIGHT COMM LOOP</div>
              <div className="ls-comm-log">
                {seq.log.map((l, i) => (
                  <div key={i} className="ls-comm-line">
                    <span className={`ls-who who-${l.who}`}>{l.who}</span> {l.msg}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Decision panel */}
        {decision && (
          <div className={`ls-decision ${decision.severe ? "severe" : ""}`}>
            <div className="ls-dec-head">
              <span className="ls-dec-alert">⚠ {decision.title}</span>
              <CountdownBar timeLeft={decision.timeLeft} deadline={decision.deadline} />
            </div>
            <div className="ls-dec-detail">{decision.detail}</div>
            <div className="ls-dec-feedback">📡 {decision.crewFeedback}</div>
            <div className="ls-dec-options">
              {decision.options.map((o) => (
                <button key={o.id}
                  className={`ls-opt ${o.id === "ABORT" ? "abort" : ""}`}
                  onClick={() => conn.launchDecision(seq.contractId, o.id)}>
                  <b>{o.label}</b>
                  {o.hint && <span>{o.hint}</span>}
                </button>
              ))}
            </div>
            <div className="ls-dec-note">
              Decide before the timer expires — or the crew handles it alone on their composure.
            </div>
          </div>
        )}

        {/* Outcome */}
        {done && (
          <div className={`ls-outcome ${outcomeClass(seq.result)}`}>
            <div className="ls-outcome-title">{outcomeTitle(seq.result)}</div>
            <div className="ls-outcome-detail">{seq.outcome}</div>
            <button className="btn primary" onClick={() => conn.dismissLaunch(seq.contractId)}>
              RETURN TO MISSION CONTROL
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Tele({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="ls-tele">
      <span className="ls-tele-label">{label}</span>
      <span className={`ls-tele-value ${warn ? "warn" : ""}`}>{value}</span>
    </div>
  );
}

function CountdownBar({ timeLeft, deadline }: { timeLeft: number; deadline: number }) {
  const pct = Math.max(0, Math.min(100, (timeLeft / deadline) * 100));
  const band = pct > 50 ? "ok" : pct > 25 ? "warn" : "crit";
  return (
    <div className="ls-countdown">
      <span className={`ls-cd-num ${band}`}>{timeLeft.toFixed(0)}s</span>
      <div className="ls-cd-track"><div className={`ls-cd-fill ${band}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function AscentGauge({ altitudeKm }: { altitudeKm: number }) {
  const H = 460;
  const frac = Math.min(1, altitudeKm / MAX_ALT);
  const rocketY = H - 30 - frac * (H - 60);
  // atmosphere bands (km ranges → fraction of MAX_ALT)
  const bands = [
    { name: "SPACE", from: 100, to: MAX_ALT, color: "#05070d" },
    { name: "THERMOSPHERE", from: 85, to: 100, color: "#0b1322" },
    { name: "MESOSPHERE", from: 50, to: 85, color: "#101c33" },
    { name: "STRATOSPHERE", from: 12, to: 50, color: "#16294a" },
    { name: "TROPOSPHERE", from: 0, to: 12, color: "#1d3a66" },
  ];
  const yOf = (km: number) => H - 30 - (Math.min(km, MAX_ALT) / MAX_ALT) * (H - 60);
  return (
    <svg viewBox={`0 0 150 ${H}`} className="ls-gauge">
      {bands.map((b) => {
        const y1 = yOf(b.to), y2 = yOf(b.from);
        return (
          <g key={b.name}>
            <rect x="0" y={y1} width="150" height={y2 - y1} fill={b.color} />
            <line x1="0" y1={y2} x2="150" y2={y2} stroke="#2a3a55" strokeWidth="0.5" />
            <text x="6" y={y2 - 3} fill="#5a7396" fontSize="7">{b.name}</text>
          </g>
        );
      })}
      {/* ground */}
      <rect x="0" y={H - 30} width="150" height="30" fill="#1a1208" />
      {/* rocket */}
      <g transform={`translate(75 ${rocketY})`}>
        <polygon points="0,-10 4,4 -4,4" fill="#dcf0ff" />
        <rect x="-3" y="4" width="6" height="10" fill="#aad2ff" />
        <polygon points="0,16 4,10 -4,10" fill="#ff9632" />
      </g>
      <text x="144" y={rocketY} fill="#aad2ff" fontSize="8" textAnchor="end">
        {altitudeKm.toFixed(0)}km
      </text>
    </svg>
  );
}

function outcomeClass(r: string | null) {
  if (r === "SUCCESS") return "success";
  if (r === "DEGRADED") return "degraded";
  if (r === "ABORT") return "abort";
  return "fail";
}
function outcomeTitle(r: string | null) {
  return {
    SUCCESS: "✓ MISSION SUCCESS",
    DEGRADED: "◐ PARTIAL SUCCESS",
    ABORT: "⊘ LAUNCH ABORTED",
    FAILURE: "✗ VEHICLE LOST",
  }[r ?? ""] ?? "FLIGHT COMPLETE";
}
