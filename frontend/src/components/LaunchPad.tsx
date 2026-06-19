import { useEffect, useState } from "react";
import type { GameConnection } from "../useGameSocket";
import type { Contract, CraftSpec, Issue, ActiveTask, LaunchOdds } from "../types";
import { getLaunchSites, type LaunchSite } from "../api";

const OPS: { op: string; label: string; cost: number; days: number; crewOnly?: boolean }[] = [
  { op: "DRY_RUN", label: "Design Review", cost: 5, days: 1 },
  { op: "SYSTEMS_TEST", label: "Systems Test", cost: 15, days: 3 },
  { op: "WET_RUN", label: "Wet Rehearsal", cost: 40, days: 4 },
  { op: "STATIC_BURN", label: "Static Fire", cost: 60, days: 6 },
  { op: "ASTRO_TRAINING", label: "Astro Training", cost: 20, days: 21, crewOnly: true },
];
const LAUNCH_COST = 50;
const DAY = 86400;

interface Props {
  conn: GameConnection;
  onBack: () => void;
}

// Contracts that have a vehicle and belong at the pad (test + launch).
const AT_PAD = ["VEHICLE_ASSIGNED", "READY", "LAUNCHED"];

export function LaunchPad({ conn, onBack }: Props) {
  const st = conn.state;
  const contracts = (st?.contracts ?? []).filter(
    (c) => c.craftName && AT_PAD.includes(c.status));
  const crafts = st?.crafts ?? [];
  const [selId, setSelId] = useState<string | null>(null);
  const [sites, setSites] = useState<LaunchSite[]>([]);
  const selected = contracts.find((c) => c.id === selId) ?? null;

  useEffect(() => { getLaunchSites().then(setSites).catch(() => {}); }, []);
  useEffect(() => {
    if (!selId && contracts.length) setSelId(contracts[0].id);
  }, [contracts, selId]);

  return (
    <div className="launchpad">
      <div className="lp-body">
        <div className="panel lp-board">
          <div className="panel-head">LAUNCH PAD · VEHICLES</div>
          <div className="panel-body">
            {contracts.length === 0 && (
              <div className="empty-hint">
                No vehicles at the pad. Assign a vehicle to a mission in
                <b> Operations</b> first.
              </div>
            )}
            {contracts.map((c) => (
              <div key={c.id} className={`contract-row ${selId === c.id ? "sel" : ""}`}
                onClick={() => setSelId(c.id)}>
                <div className="cr-top">
                  <span className="cr-title">{c.title}</span>
                  <span className={`cstatus s-${c.status}`}>{c.status.replace("_", " ")}</span>
                </div>
                <div className="cr-sub">{c.craftName} · {c.origin} → {c.destination}</div>
                <div className="cr-req">
                  {c.launchOdds
                    ? `success ${Math.round(c.launchOdds.successProbability * 100)}%`
                    : c.outcome ? c.outcome.split(":")[0] : "awaiting prep"}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel lp-main">
          <div className="panel-head">
            {selected ? `${selected.id} · ${selected.title}` : "LAUNCH PAD"}
          </div>
          {!selected ? (
            <div className="panel-body"><div className="empty-hint">
              Select a vehicle. Run test operations, correct findings, then launch.
            </div></div>
          ) : (
            <div className="panel-body lp-flow">
              <PadStep c={selected} sites={sites} conn={conn} funds={st?.funds ?? 0}
                craft={crafts.find((k) => k.name === selected.craftName)} />
            </div>
          )}
        </div>
      </div>

      <div className="lp-bar">
        <button className="btn back" onClick={onBack}>◄ BACK TO COMMAND CENTER</button>
        <span className="lp-hint">
          Launch Pad: site &amp; time · scheduled test runs · correct findings · launch on the odds
        </span>
      </div>
    </div>
  );
}

function PadStep({ c, sites, conn, funds, craft }: {
  c: Contract; sites: LaunchSite[]; conn: GameConnection; funds: number; craft?: CraftSpec;
}) {
  const winT = c.chosenWindow?.departTime ?? 0;
  const launchT = c.plannedLaunchTime ?? winT;
  const offDays = winT ? (launchT - winT) / DAY : 0;
  const setTime = (t: number) => { if (c.launchSiteId) conn.setLaunch(c.id, c.launchSiteId, t); };

  const openIssues = c.issues.filter((i) => !i.corrected);
  const blockingFaults = (c.lastDryRun?.checks ?? []).filter((ch) => ch.severity === "FAIL");
  const busy = !!c.activeTask;
  const canLaunch = c.status === "READY" && c.designOk && funds >= LAUNCH_COST
    && !busy && !c.windowMissed && !c.conflict;
  const over = c.spent > c.budget;
  const odds = c.launchOdds;
  const pct = odds ? Math.round(odds.successProbability * 100) : null;

  if (c.status === "LAUNCHED") {
    const failed = c.outcome?.startsWith("FAILURE");
    const degraded = c.outcome?.startsWith("DEGRADED");
    return (
      <div className="step-content pad">
        <div className={`launch-result ${failed ? "fail" : degraded ? "degraded" : "success"}`}>
          {failed ? "✗ LAUNCH FAILURE" : degraded ? "◐ PARTIAL SUCCESS" : "✓ MISSION SUCCESS"}
        </div>
        <div className="lr-detail">{c.outcome}</div>
        {c.missionName && <div className="ok-note">Mission {c.missionName} is now tracked in the Command Center fleet.</div>}
      </div>
    );
  }

  return (
    <div className="step-content pad">
      {/* Budget + window */}
      <div className="budget-bar">
        <div className="bb-row">
          <span className="bb-label">CONGRESSIONAL BUDGET</span>
          <span className={`bb-val ${over ? "over" : ""}`}>
            §{c.spent.toFixed(0)}M / §{c.budget.toFixed(0)}M{over ? " · OVER BUDGET" : ""}
          </span>
          <span className="bb-window">
            {c.windowMissed ? "⚠ WINDOW MISSED — re-plan in Operations"
              : c.daysToWindow != null ? `launch window in ${c.daysToWindow.toFixed(0)} d` : ""}
          </span>
        </div>
        <div className="bb-track">
          <div className={`bb-fill ${over ? "over" : ""}`}
            style={{ width: `${Math.min(100, (c.spent / Math.max(1, c.budget)) * 100)}%` }} />
        </div>
      </div>

      {/* Flight profile */}
      {craft?.flight && (
        <div className="flight-profile">
          <div className="fp-head">
            <span className="fp-label">FLIGHT PROFILE · {craft.name}</span>
            <span className={`flight-badge fv-${craft.flight.verdict.replace(/[^A-Z]/g, "")}`}>
              {craft.flight.verdict}
            </span>
            <span className="fp-meta">
              {craft.flight.stability} · margin {craft.flight.staticMarginCal.toFixed(2)} cal ·
              fineness {craft.flight.finenessRatio.toFixed(1)}:1 · max-Q {craft.flight.maxQLevel}
            </span>
          </div>
          {craft.flight.issues.map((i) => (
            <div key={i.code} className={`fp-issue sev-${i.severity}`}>
              <span className="wt-sev">{i.severity}</span> {i.title}
            </div>
          ))}
        </div>
      )}

      {c.conflict && (
        <div className="conflict-banner">
          ⚠ SLOT CONFLICT — pad {c.conflict.siteId} also claimed by
          <b> {c.conflict.withTitle}</b> ({c.conflict.withOwner}). One of you must move pad/date.
        </div>
      )}

      <div className="section-label">LAUNCH SITE {c.conflict ? "— move to resolve conflict" : ""}</div>
      <div className="site-grid">
        {sites.map((s) => (
          <button key={s.id} className={`site ${c.launchSiteId === s.id ? "sel" : ""}`}
            onClick={() => conn.setLaunch(c.id, s.id, launchT)}>
            <b>{s.short}</b><span>{s.country} · {s.latitude.toFixed(1)}°</span>
          </button>
        ))}
      </div>

      {!c.launchSiteId ? (
        <div className="dim">Select a launch site to continue.</div>
      ) : (
        <>
          <div className="section-label">ANTICIPATED LAUNCH TIME</div>
          <div className="time-ctrl">
            <span className="t-date">{c.plannedLaunchDate}</span>
            <span className="t-off dim">
              {offDays === 0 ? "on optimal window" : `${offDays > 0 ? "+" : ""}${offDays.toFixed(0)} d from window`}
            </span>
            <div className="t-buttons">
              <button onClick={() => setTime(launchT - 7 * DAY)}>−7d</button>
              <button onClick={() => setTime(launchT - DAY)}>−1d</button>
              <button onClick={() => setTime(winT)}>Snap to window</button>
              <button onClick={() => setTime(launchT + DAY)}>+1d</button>
              <button onClick={() => setTime(launchT + 7 * DAY)}>+7d</button>
            </div>
          </div>

          {(c.activeTask || c.queue.length > 0) && (
            <SchedulePanel active={c.activeTask} queue={c.queue}
              onCancel={(tid) => conn.cancelTask(c.id, tid)} />
          )}

          <div className="section-label">
            TEST RUNS — scheduled in real time · queue stacks up · cancel anytime
          </div>
          <div className="ops-grid">
            {OPS.filter((o) => !o.crewOnly || c.requiredCrew > 0).map((o) => {
              const inspected = c.opsRun.includes(o.op) || (o.op === "DRY_RUN" && c.dryRunCount > 0);
              const poor = funds < o.cost;
              return (
                <button key={o.op} className={`op ${inspected ? "done" : ""} ${poor ? "poor" : ""}`}
                  disabled={poor} onClick={() => conn.runOperation(c.id, o.op)}>
                  <b>{o.label}</b>
                  <span>§{o.cost}M · {o.days}d{busy ? " · queue" : ""}</span>
                </button>
              );
            })}
          </div>

          {c.lastDryRun && (
            <div className="design-review">
              <div className={`dr-banner ${c.designOk ? "ready" : "blocked"}`}>
                {c.designOk
                  ? `✓ DESIGN REVIEW PASSED (#${c.lastDryRun.attempt})`
                  : `✗ DESIGN REVIEW — ${blockingFaults.length} BLOCKING FAULT(S) · fix in Vehicle Assembly`}
              </div>
              {blockingFaults.map((ch, i) => (
                <div key={i} className="dr-check sev-FAIL">
                  <div className="dc-head"><span className="dc-sev">FAIL</span>
                    <span className="dc-name">{ch.name}</span></div>
                  <div className="dc-msg">{ch.message}</div>
                  {ch.fix && <div className="dc-fix">→ {ch.fix}</div>}
                </div>
              ))}
            </div>
          )}

          <div className="section-label">
            FINDINGS — correct (cost + delay) or fly with them (each lowers the odds)
          </div>
          {openIssues.length === 0 ? (
            <div className="dim">No open findings. Run more test runs to inspect un-checked subsystems.</div>
          ) : (
            openIssues.map((iss) => (
              <IssueRow key={iss.id} iss={iss} funds={funds}
                onCorrect={() => conn.correctIssue(c.id, iss.id)} />
            ))
          )}

          {/* Success odds */}
          {odds && <OddsPanel odds={odds} />}

          <div className="dryrun-bar">
            <button className={`btn launch ${canLaunch ? "" : "disabled"}`}
              disabled={!canLaunch} onClick={() => conn.launchContract(c.id)}>
              🚀 LAUNCH (§{LAUNCH_COST}M){pct != null ? ` · ${pct}% success` : ""}
            </button>
            {c.conflict && <span className="dim alert">Resolve the slot conflict first.</span>}
            {!c.conflict && busy && <span className="dim">Test run in progress — wait or cancel.</span>}
            {!c.conflict && !busy && !c.designOk && <span className="dim">Pass a design review (dry run) first.</span>}
          </div>
        </>
      )}
    </div>
  );
}

function OddsPanel({ odds }: { odds: LaunchOdds }) {
  const pct = Math.round(odds.successProbability * 100);
  const band = pct >= 85 ? "low" : pct >= 60 ? "med" : "high";
  return (
    <div className="odds-panel">
      <div className="op-row">
        <span className="op-label">PREDICTED LAUNCH SUCCESS</span>
        <span className={`op-pct rm-val ${band}`}>{pct}%</span>
        <span className="op-crew">crew: {odds.crew.label} · composure {Math.round(odds.crew.composure * 100)}%</span>
      </div>
      <div className="rm-bar">
        <div className={`rm-fill ${band}`} style={{ width: `${pct}%` }} />
      </div>
      {odds.sources.length === 0 ? (
        <div className="op-clean dim">No outstanding risk factors — clean flight predicted.</div>
      ) : (
        <div className="op-sources">
          {odds.sources.map((s, i) => (
            <div key={i} className="op-src">
              <span className="op-src-label">{s.label}</span>
              <span className="op-src-chance">−{Math.round(s.chance * 100)}%</span>
            </div>
          ))}
        </div>
      )}
      <div className="op-note dim">
        Odds combine open findings, un-inspected subsystems, vehicle wear, and flight
        characteristics. Astronaut skill &amp; composure (placeholder for now) avert and recover
        anomalies — to be expanded when the astronaut corps is modelled.
      </div>
    </div>
  );
}

function IssueRow({ iss, funds, onCorrect }: {
  iss: Issue; funds: number; onCorrect: () => void;
}) {
  const refurb = iss.category === "Refurbishment";
  const poor = funds < iss.correctionCost;
  return (
    <div className="issue-row">
      <div className="ir-main">
        <span className="ir-cat">{iss.category}</span>
        <span className="ir-desc">{iss.description}</span>
      </div>
      <div className="ir-side">
        {!refurb && (
          <span className="ir-risk" title="chance of striking during the mission if left">
            {(iss.failureChance * 100).toFixed(0)}% risk
          </span>
        )}
        <button className={`ir-fix ${poor ? "poor" : ""}`} disabled={poor} onClick={onCorrect}>
          QUEUE REPAIR · §{iss.correctionCost}M · {iss.correctionDays}d
        </button>
      </div>
    </div>
  );
}

function SchedulePanel({ active, queue, onCancel }: {
  active: ActiveTask | null; queue: ActiveTask[]; onCancel: (taskId: string) => void;
}) {
  return (
    <div className="active-task">
      {active && (
        <>
          <div className="at-row">
            <span className="at-spin" />
            <span className="at-label">IN PROGRESS · {active.label}</span>
            <span className="at-eta">{active.remainingDays.toFixed(1)} d left</span>
            <button className="at-cancel" onClick={() => onCancel(active.id)}>ABORT</button>
          </div>
          <div className="at-track">
            <div className="at-fill" style={{ width: `${Math.round(active.progress * 100)}%` }} />
          </div>
        </>
      )}
      {queue.length > 0 && (
        <div className="queue-list">
          <div className="ql-label">QUEUED ({queue.length})</div>
          {queue.map((t, i) => (
            <div className="ql-row" key={t.id}>
              <span className="ql-pos">{i + 1}</span>
              <span className="ql-label-txt">{t.label}</span>
              <span className="ql-meta dim">§{t.cost.toFixed(0)}M · {t.durationDays.toFixed(0)}d</span>
              <button className="ql-cancel" onClick={() => onCancel(t.id)}>cancel</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
