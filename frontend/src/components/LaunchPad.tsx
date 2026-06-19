import { useEffect, useState } from "react";
import type { GameConnection } from "../useGameSocket";
import type { Contract, CraftSpec, DryCheck, Issue, ActiveTask } from "../types";

const MAX_LAUNCHES = 5;
import { getLaunchSites, getWindows, type LaunchSite, type WindowOption } from "../api";

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

const STEP_LABELS = ["1 · Accept", "2 · Plan", "3 · Vehicle", "4 · Launch Pad"];

function naturalStep(c: Contract): number {
  switch (c.status) {
    case "AVAILABLE": return 0;
    case "ACCEPTED": return 1;
    case "PLANNED": return 2;
    default: return 3; // VEHICLE_ASSIGNED / READY / LAUNCHED
  }
}

export function LaunchPad({ conn, onBack }: Props) {
  const st = conn.state;
  const contracts = st?.contracts ?? [];
  const crafts = st?.crafts ?? [];

  const [selId, setSelId] = useState<string | null>(null);
  const [viewStep, setViewStep] = useState(0);
  const [sites, setSites] = useState<LaunchSite[]>([]);
  const [windows, setWindows] = useState<WindowOption[]>([]);

  const selected = contracts.find((c) => c.id === selId) ?? null;

  // auto-select first contract
  useEffect(() => {
    if (!selId && contracts.length) setSelId(contracts[0].id);
  }, [contracts, selId]);

  // load launch sites once
  useEffect(() => { getLaunchSites().then(setSites).catch(() => {}); }, []);

  // load transfer windows when selection changes
  useEffect(() => {
    if (selected) {
      getWindows(selected.origin, selected.destination).then(setWindows).catch(() => setWindows([]));
      setViewStep(naturalStep(selected));
    }
  }, [selId, selected?.status]);

  return (
    <div className="launchpad">
      <div className="lp-body">
        <MissionBoard
          contracts={contracts}
          selId={selId}
          onSelect={setSelId}
          onAccept={conn.acceptContract}
          scheduled={contracts.filter((c) =>
            c.ownerId === conn.playerId && c.launchSiteId &&
            (c.status === "VEHICLE_ASSIGNED" || c.status === "READY")).length}
        />

        <div className="panel lp-main">
          <div className="panel-head">
            {selected ? `${selected.id} · ${selected.title}` : "LAUNCH OPERATIONS"}
          </div>
          {!selected ? (
            <div className="panel-body"><div className="empty-hint">Select a mission from the board.</div></div>
          ) : (
            <div className="panel-body lp-flow">
              <StepBar contract={selected} viewStep={viewStep} onStep={setViewStep} />
              {viewStep === 0 && <AcceptStep c={selected} onAccept={conn.acceptContract} />}
              {viewStep === 1 && (
                <PlanStep c={selected} windows={windows} onPlan={conn.planContract} />
              )}
              {viewStep === 2 && (
                <VehicleStep c={selected} crafts={crafts} onAssign={conn.assignCraft} />
              )}
              {viewStep === 3 && (
                <PadStep c={selected} sites={sites} conn={conn} funds={st?.funds ?? 0}
                  craft={crafts.find((k) => k.name === selected.craftName)} />
              )}
            </div>
          )}
        </div>
      </div>

      <div className="lp-bar">
        <button className="btn back" onClick={onBack}>◄ BACK TO COMMAND CENTER</button>
        <span className="lp-hint">
          Accept → Plan window → Assign vehicle → Run dry runs at the pad → fix issues → Launch
        </span>
      </div>
    </div>
  );
}

// ── Mission board ─────────────────────────────────────────────────────────────

function statusClass(s: string) {
  return `cstatus s-${s}`;
}

function MissionBoard({
  contracts, selId, onSelect, onAccept, scheduled,
}: {
  contracts: Contract[]; selId: string | null;
  onSelect: (id: string) => void; onAccept: (id: string) => void; scheduled: number;
}) {
  return (
    <div className="panel lp-board">
      <div className="panel-head">
        <span>MISSION BOARD</span>
        <span className={scheduled >= MAX_LAUNCHES ? "sched-cap full" : "sched-cap"}>
          launches {scheduled}/{MAX_LAUNCHES}
        </span>
      </div>
      <div className="panel-body">
        {contracts.map((c) => (
          <div
            key={c.id}
            className={`contract-row ${selId === c.id ? "sel" : ""}`}
            onClick={() => onSelect(c.id)}
          >
            <div className="cr-top">
              <span className="cr-title">{c.title}</span>
              <span className={statusClass(c.status)}>{c.status.replace("_", " ")}</span>
            </div>
            <div className="cr-sub">
              {c.origin} → {c.destination} · {c.objective}
            </div>
            <div className="cr-req">
              ΔV {c.requiredDeltaV.toLocaleString()} m/s
              {c.requiredCrew > 0 ? ` · ${c.requiredCrew} crew` : ""}
              {c.source === "GENERATOR" ? "" : " · player"}
            </div>
            {c.status === "AVAILABLE" && (
              <button className="mini accept" onClick={(e) => { e.stopPropagation(); onAccept(c.id); }}>
                ACCEPT
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Step bar ──────────────────────────────────────────────────────────────────

function StepBar({ contract, viewStep, onStep }: {
  contract: Contract; viewStep: number; onStep: (s: number) => void;
}) {
  const reached = naturalStep(contract);
  return (
    <div className="stepbar">
      {STEP_LABELS.map((lbl, i) => {
        const done = i < reached;
        const active = i === viewStep;
        const reachable = i <= reached;
        return (
          <button
            key={i}
            className={`step ${active ? "active" : ""} ${done ? "done" : ""} ${reachable ? "" : "locked"}`}
            onClick={() => reachable && onStep(i)}
            disabled={!reachable}
          >
            {done ? "✓ " : ""}{lbl}
          </button>
        );
      })}
    </div>
  );
}

// ── Step 1: Accept ────────────────────────────────────────────────────────────

function AcceptStep({ c, onAccept }: { c: Contract; onAccept: (id: string) => void }) {
  return (
    <div className="step-content">
      <p className="desc">{c.description}</p>
      <div className="kv">
        <span>Route</span><b>{c.origin} → {c.destination}</b>
        <span>Objective</span><b>{c.objective}</b>
        <span>Required ΔV</span><b>{c.requiredDeltaV.toLocaleString()} m/s</b>
        <span>Crew</span><b>{c.requiredCrew || "uncrewed"}</b>
        <span>Payload</span><b>{c.payloadKeywords.slice(0, 4).join(" / ")}</b>
        <span>Reward</span><b>§{c.reward}M</b>
      </div>
      {c.status === "AVAILABLE" ? (
        <button className="btn primary" onClick={() => onAccept(c.id)}>ACCEPT CONTRACT</button>
      ) : (
        <div className="ok-note">✓ Contract accepted — proceed to planning.</div>
      )}
    </div>
  );
}

// ── Step 2: Plan ──────────────────────────────────────────────────────────────

function PlanStep({ c, windows, onPlan }: {
  c: Contract; windows: WindowOption[]; onPlan: (id: string, idx: number) => void;
}) {
  return (
    <div className="step-content">
      <div className="section-label">SELECT A TRANSFER WINDOW ({c.origin} → {c.destination})</div>
      {windows.length === 0 && <div className="dim">Loading windows…</div>}
      {windows.map((w, i) => {
        const chosen = c.chosenWindow?.departDate === w.departDate;
        return (
          <div
            key={i}
            className={`window-row ${chosen ? "sel" : ""}`}
            onClick={() => onPlan(c.id, i)}
          >
            <span className="w-depart">{w.departDate}</span>
            <span className="w-arrow">→</span>
            <span className="w-arrive">{w.arriveDate}</span>
            <span className="w-dur">{w.durationDays} d</span>
            <span className="w-dv">{w.dvTotal.toLocaleString()} m/s</span>
            <span className={`w-q q-${w.quality}`}>{w.quality}</span>
            {chosen && <span className="w-chosen">✓ planned</span>}
          </div>
        );
      })}
      {c.chosenWindow && (
        <div className="ok-note">
          ✓ Planned: depart {c.chosenWindow.departDate}, arrive {c.chosenWindow.arriveDate}
          ({c.chosenWindow.durationDays} d). Proceed to vehicle assignment.
        </div>
      )}
    </div>
  );
}

// ── Step 3: Vehicle ───────────────────────────────────────────────────────────

function craftMeets(c: Contract, k: CraftSpec) {
  const dv = k.totalDeltaV >= c.requiredDeltaV;
  const crew = k.crew >= c.requiredCrew;
  const blob = k.partNames.join(" ").toLowerCase();
  const payload = c.payloadKeywords.length === 0 ||
    c.payloadKeywords.some((p) => blob.includes(p.toLowerCase()));
  const twr = k.twr >= 1.05;
  return { dv, crew, payload, twr, all: dv && crew && payload && twr };
}

function VehicleStep({ c, crafts, onAssign }: {
  c: Contract; crafts: CraftSpec[]; onAssign: (id: string, name: string) => void;
}) {
  return (
    <div className="step-content">
      <div className="section-label">ASSIGN A VEHICLE (specs vs mission requirements)</div>
      {crafts.length === 0 && (
        <div className="empty-hint">
          No saved craft. Build one in <b>Vehicle Assembly</b> first.
        </div>
      )}
      {crafts.map((k) => {
        const m = craftMeets(c, k);
        const assigned = c.craftName === k.name;
        return (
          <div
            key={k.name}
            className={`craft-row ${assigned ? "sel" : ""} ${m.all ? "" : "short"}`}
            onClick={() => onAssign(c.id, k.name)}
          >
            <div className="ck-top">
              <span className="ck-name">{k.name}</span>
              <span className="ck-stages">{k.stages} stage{k.stages > 1 ? "s" : ""}</span>
              {k.flight && (
                <span className={`flight-badge fv-${k.flight.verdict.replace(/[^A-Z]/g, "")}`}
                  title={k.flight.issues.map((i) => i.title).join(" · ") || "No adverse characteristics"}>
                  {k.flight.verdict}
                </span>
              )}
              {assigned && <span className="ck-assigned">✓ assigned</span>}
            </div>
            <div className="ck-checks">
              <Check ok={m.dv} label={`ΔV ${k.totalDeltaV.toLocaleString()}`} />
              <Check ok={m.twr} label={`TWR ${k.twr.toFixed(2)}`} />
              <Check ok={m.crew} label={`crew ${k.crew}`} />
              <Check ok={m.payload} label="payload" />
              <span className="ck-mass">{k.totalMassTons} t</span>
            </div>
          </div>
        );
      })}
      {c.craftName && (
        <div className="ok-note">✓ Vehicle '{c.craftName}' assigned — head to the Launch Pad.</div>
      )}
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`ck ${ok ? "ok" : "no"}`}>{ok ? "✓" : "✗"} {label}</span>;
}

// ── Step 4: Launch Pad ────────────────────────────────────────────────────────

function PadStep({ c, sites, conn, funds, craft }: {
  c: Contract; sites: LaunchSite[]; conn: GameConnection; funds: number; craft?: CraftSpec;
}) {
  const winT = c.chosenWindow?.departTime ?? 0;
  const launchT = c.plannedLaunchTime ?? winT;
  const offDays = winT ? (launchT - winT) / DAY : 0;
  const setTime = (t: number) => { if (c.launchSiteId) conn.setLaunch(c.id, c.launchSiteId, t); };

  const risk = c.missionRisk;
  const openIssues = c.issues.filter((i) => !i.corrected);
  const blockingFaults = (c.lastDryRun?.checks ?? []).filter((ch) => ch.severity === "FAIL");
  const busy = !!c.activeTask;
  const canLaunch = c.status === "READY" && c.designOk && funds >= LAUNCH_COST
    && !busy && !c.windowMissed;
  const over = c.spent > c.budget;

  return (
    <div className="step-content pad">
      {/* Budget + window status */}
      <div className="budget-bar">
        <div className="bb-row">
          <span className="bb-label">CONGRESSIONAL BUDGET</span>
          <span className={`bb-val ${over ? "over" : ""}`}>
            §{c.spent.toFixed(0)}M / §{c.budget.toFixed(0)}M{over ? " · OVER BUDGET" : ""}
          </span>
          <span className="bb-window">
            {c.windowMissed
              ? "⚠ WINDOW MISSED — re-plan"
              : c.daysToWindow != null
                ? `launch window in ${c.daysToWindow.toFixed(0)} d`
                : ""}
          </span>
        </div>
        <div className="bb-track">
          <div className={`bb-fill ${over ? "over" : ""}`}
            style={{ width: `${Math.min(100, (c.spent / Math.max(1, c.budget)) * 100)}%` }} />
        </div>
        {over && <div className="bb-warn">Overrun triggers a congressional penalty to your next mission's allotment.</div>}
      </div>

      {/* Flight profile (wind-tunnel) of the assigned vehicle */}
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
          {craft.flight.issues.length === 0 ? (
            <div className="fp-clean">✓ No adverse flight characteristics.</div>
          ) : (
            craft.flight.issues.map((i) => (
              <div key={i.code} className={`fp-issue sev-${i.severity}`}>
                <span className="wt-sev">{i.severity}</span> {i.title}
              </div>
            ))
          )}
          {craft.flight.flightEvents.length > 0 && (
            <div className="fp-events">
              In-flight risk: {craft.flight.flightEvents
                .map((e) => `${e.description} (${Math.round(e.chance * 100)}%)`).join(" · ")}
            </div>
          )}
        </div>
      )}

      {c.conflict && (
        <div className="conflict-banner">
          ⚠ SLOT CONFLICT — pad {c.conflict.siteId} is also claimed by
          <b> {c.conflict.withTitle}</b> ({c.conflict.withOwner}) within the
          3-day pad turnaround. Neither can launch until one of you moves to a
          different pad or date.
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

          {/* Active + queued tasks */}
          {(c.activeTask || c.queue.length > 0) && (
            <SchedulePanel active={c.activeTask} queue={c.queue}
              onCancel={(tid) => conn.cancelTask(c.id, tid)} />
          )}

          {/* Test operations (scheduled / queued) */}
          <div className="section-label">
            TEST OPERATIONS — scheduled in real time · queue stacks up · cancel anytime
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

          {/* Risk meter */}
          <RiskMeter risk={risk} wear={c.vehicleWear} />

          {/* Design review (dry run) */}
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

          {/* Surfaced issues */}
          <div className="section-label">
            SURFACED ISSUES — correct (cost + delay) or gamble (carries mission risk)
          </div>
          {openIssues.length === 0 ? (
            <div className="dim">No open issues. Run more tests to inspect un-checked subsystems
              {c.opsRun.length < 3 ? " (lowers hidden risk)." : "."}</div>
          ) : (
            openIssues.map((iss) => (
              <IssueRow key={iss.id} iss={iss} funds={funds}
                onCorrect={() => conn.correctIssue(c.id, iss.id)} />
            ))
          )}
          {c.issues.some((i) => i.corrected) && (
            <div className="corrected-note">
              ✓ {c.issues.filter((i) => i.corrected).length} issue(s) corrected
            </div>
          )}

          {/* Launch */}
          <div className="dryrun-bar">
            <button className={`btn launch ${canLaunch ? "" : "disabled"}`}
              disabled={!canLaunch} onClick={() => conn.launchContract(c.id)}>
              🚀 LAUNCH (§{LAUNCH_COST}M) · {(risk * 100).toFixed(0)}% mission risk
            </button>
            {c.conflict && <span className="dim alert">Resolve the slot conflict first.</span>}
            {!c.conflict && busy && <span className="dim">Operations queued — wait or cancel them.</span>}
            {!c.conflict && !busy && c.windowMissed && <span className="dim">Window missed — re-plan (step 2).</span>}
            {!c.conflict && !busy && !c.windowMissed && !c.designOk && <span className="dim">Pass a design review first.</span>}
          </div>

          {c.status === "LAUNCHED" && (
            <div className={`ok-note big ${c.outcome?.startsWith("ANOMALY") ? "anomaly" : ""}`}>
              {c.outcome?.startsWith("ANOMALY") ? "⚠ " : "✓ "}
              LAUNCHED — mission {c.missionName}. {c.outcome}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function RiskMeter({ risk, wear }: { risk: number; wear: number }) {
  const pct = Math.round(risk * 100);
  const band = pct < 15 ? "low" : pct < 35 ? "med" : "high";
  return (
    <div className="risk-meter">
      <div className="rm-row">
        <span className="rm-label">MISSION RISK</span>
        <span className={`rm-val ${band}`}>{pct}%</span>
        {wear > 0 && <span className="rm-wear">vehicle wear {wear.toFixed(0)}%</span>}
      </div>
      <div className="rm-bar">
        <div className={`rm-fill ${band}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <div className="rm-hint dim">
        Each un-corrected issue and un-inspected subsystem adds risk. Testing reveals issues;
        correcting them lowers risk but costs funds and slips the launch date.
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
      <div className="at-hint dim">
        Other crafts run their own operations at the same time. Advance time-warp to fast-forward the queue.
      </div>
    </div>
  );
}
