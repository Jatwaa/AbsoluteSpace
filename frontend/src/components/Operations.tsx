import { useEffect, useState } from "react";
import type { GameConnection } from "../useGameSocket";
import type { Contract, CraftSpec } from "../types";
import { getWindows, type WindowOption } from "../api";

interface Props {
  conn: GameConnection;
  onBack: () => void;
  onGoToPad: () => void;
}

const SOURCE_LABEL: Record<string, string> = {
  HISTORICAL: "HISTORICAL PROGRAMS",
  CONGRESS: "CONGRESSIONAL TASKING",
};

export function Operations({ conn, onBack, onGoToPad }: Props) {
  const st = conn.state;
  const contracts = st?.contracts ?? [];
  const crafts = st?.crafts ?? [];

  const [selId, setSelId] = useState<string | null>(null);
  const [windows, setWindows] = useState<WindowOption[]>([]);
  const selected = contracts.find((c) => c.id === selId) ?? null;

  useEffect(() => {
    if (selected) getWindows(selected.origin, selected.destination)
      .then(setWindows).catch(() => setWindows([]));
  }, [selId, selected?.destination]);

  // group the board
  const available = contracts.filter((c) => c.status === "AVAILABLE");
  const mine = contracts.filter((c) =>
    c.status !== "AVAILABLE" && c.status !== "LAUNCHED" && c.ownerId === conn.playerId);
  const histAvail = available.filter((c) => c.source === "HISTORICAL");
  const congAvail = available.filter((c) => c.source === "CONGRESS");

  return (
    <div className="launchpad">
      <div className="lp-body">
        <div className="panel lp-board">
          <div className="panel-head">OPERATIONS · MISSION BOARD</div>
          <div className="panel-body">
            {mine.length > 0 && (
              <Section title="IN PROGRESS">
                {mine.map((c) => (
                  <ContractRow key={c.id} c={c} sel={selId === c.id} onSelect={setSelId} />
                ))}
              </Section>
            )}
            <Section title={SOURCE_LABEL.HISTORICAL}>
              {histAvail.map((c) => (
                <ContractRow key={c.id} c={c} sel={selId === c.id} onSelect={setSelId}
                  onAccept={conn.acceptContract} />
              ))}
            </Section>
            <Section title={SOURCE_LABEL.CONGRESS}>
              {congAvail.map((c) => (
                <ContractRow key={c.id} c={c} sel={selId === c.id} onSelect={setSelId}
                  onAccept={conn.acceptContract} />
              ))}
              <div className="board-note">Congressional tasking will be issued by other
                players in multiplayer.</div>
            </Section>
          </div>
        </div>

        <div className="panel lp-main">
          <div className="panel-head">
            {selected ? `${selected.id} · ${selected.title}` : "MISSION DETAIL"}
          </div>
          {!selected ? (
            <div className="panel-body"><div className="empty-hint">
              Select a mission from the board. Accept it, plan a transfer window, and assign a
              vehicle — then take it to the Launch Pad.
            </div></div>
          ) : (
            <div className="panel-body lp-flow">
              <MissionSummary c={selected} onAccept={conn.acceptContract} />
              {selected.status !== "AVAILABLE" && (
                <PlanSection c={selected} windows={windows} onPlan={conn.planContract} />
              )}
              {(selected.status === "PLANNED" || selected.status === "VEHICLE_ASSIGNED"
                || selected.status === "READY") && (
                <VehicleSection c={selected} crafts={crafts} onAssign={conn.assignCraft} />
              )}
              {(selected.status === "VEHICLE_ASSIGNED" || selected.status === "READY") && (
                <div className="to-pad">
                  <div className="ok-note">✓ Vehicle '{selected.craftName}' assigned and ready
                    for test &amp; launch operations.</div>
                  <button className="btn launch" onClick={onGoToPad}>
                    GO TO LAUNCH PAD →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="lp-bar">
        <button className="btn back" onClick={onBack}>◄ BACK TO COMMAND CENTER</button>
        <span className="lp-hint">
          Operations: accept a mission (historical or congressional) · plan the window · assign a vehicle
        </span>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="board-section">
      <div className="board-section-head">{title}</div>
      {children}
    </div>
  );
}

function ContractRow({ c, sel, onSelect, onAccept }: {
  c: Contract; sel: boolean; onSelect: (id: string) => void; onAccept?: (id: string) => void;
}) {
  return (
    <div className={`contract-row ${sel ? "sel" : ""}`} onClick={() => onSelect(c.id)}>
      <div className="cr-top">
        <span className="cr-title">{c.title}</span>
        <span className={`cstatus s-${c.status}`}>{c.status.replace("_", " ")}</span>
      </div>
      <div className="cr-sub">{c.origin} → {c.destination} · {c.objective}</div>
      <div className="cr-req">
        ΔV {c.requiredDeltaV.toLocaleString()} m/s
        {c.requiredCrew > 0 ? ` · ${c.requiredCrew} crew` : ""} · reward §{c.reward}M
      </div>
      {onAccept && c.status === "AVAILABLE" && (
        <button className="mini accept" onClick={(e) => { e.stopPropagation(); onAccept(c.id); }}>
          ACCEPT
        </button>
      )}
    </div>
  );
}

function MissionSummary({ c, onAccept }: { c: Contract; onAccept: (id: string) => void }) {
  return (
    <div className="step-content">
      <p className="desc">{c.description}</p>
      <div className="kv">
        <span>Source</span><b>{c.source === "HISTORICAL" ? "Historical program" : "Congressional tasking"}</b>
        <span>Route</span><b>{c.origin} → {c.destination}</b>
        <span>Objective</span><b>{c.objective}</b>
        <span>Required ΔV</span><b>{c.requiredDeltaV.toLocaleString()} m/s</b>
        <span>Crew</span><b>{c.requiredCrew || "uncrewed"}</b>
        <span>Payload</span><b>{c.payloadKeywords.slice(0, 4).join(" / ")}</b>
        <span>Reward</span><b>§{c.reward}M</b>
      </div>
      {c.status === "AVAILABLE" && (
        <button className="btn primary" onClick={() => onAccept(c.id)}>ACCEPT MISSION</button>
      )}
    </div>
  );
}

function PlanSection({ c, windows, onPlan }: {
  c: Contract; windows: WindowOption[]; onPlan: (id: string, idx: number) => void;
}) {
  return (
    <div className="step-content">
      <div className="section-label">TRANSFER WINDOW ({c.origin} → {c.destination})</div>
      {windows.length === 0 && <div className="dim">Loading windows…</div>}
      {windows.map((w, i) => {
        const chosen = c.chosenWindow?.departDate === w.departDate;
        return (
          <div key={i} className={`window-row ${chosen ? "sel" : ""}`} onClick={() => onPlan(c.id, i)}>
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
    </div>
  );
}

function craftMeets(c: Contract, k: CraftSpec) {
  const dv = k.totalDeltaV >= c.requiredDeltaV;
  const crew = k.crew >= c.requiredCrew;
  const blob = k.partNames.join(" ").toLowerCase();
  const payload = c.payloadKeywords.length === 0 ||
    c.payloadKeywords.some((p) => blob.includes(p.toLowerCase()));
  const twr = k.twr >= 1.05;
  return { dv, crew, payload, twr, all: dv && crew && payload && twr };
}

function VehicleSection({ c, crafts, onAssign }: {
  c: Contract; crafts: CraftSpec[]; onAssign: (id: string, name: string) => void;
}) {
  return (
    <div className="step-content">
      <div className="section-label">ASSIGN A VEHICLE (specs vs requirements)</div>
      {crafts.length === 0 && (
        <div className="empty-hint">No saved craft. Build one in <b>Vehicle Assembly</b> first.</div>
      )}
      {crafts.map((k) => {
        const m = craftMeets(c, k);
        const assigned = c.craftName === k.name;
        return (
          <div key={k.name} className={`craft-row ${assigned ? "sel" : ""} ${m.all ? "" : "short"}`}
            onClick={() => onAssign(c.id, k.name)}>
            <div className="ck-top">
              <span className="ck-name">{k.name}</span>
              <span className="ck-stages">{k.stages} stage{k.stages > 1 ? "s" : ""}</span>
              {k.flight && (
                <span className={`flight-badge fv-${k.flight.verdict.replace(/[^A-Z]/g, "")}`}>
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
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`ck ${ok ? "ok" : "no"}`}>{ok ? "✓" : "✗"} {label}</span>;
}
