import { useState } from "react";
import { useGameSocket } from "./useGameSocket";
import { CommandCenter } from "./components/CommandCenter";
import { CraftBuilder } from "./components/CraftBuilder";
import { LaunchPad } from "./components/LaunchPad";
import { Operations } from "./components/Operations";
import { DirectorPanel } from "./components/DirectorPanel";

type View = "command" | "builder" | "launchpad" | "operations";

export default function App() {
  const conn = useGameSocket();
  const st = conn.state;
  const [view, setView] = useState<View>("command");
  const [showDirector, setShowDirector] = useState(false);

  const handleFacility = (id: string) => {
    if (id.startsWith("MISSION:")) {
      // Future: open mission map focused on this craft
      return;
    }
    if (id === "OPERATIONS") {
      setView("operations");
    } else if (id === "BUILDER") {
      setView("builder");
    } else if (id === "LAUNCHPAD") {
      setView("launchpad");
    } else if (id === "MAP") {
      alert("Mission Map — coming next in the React build.");
    }
  };

  const warpLabel =
    st && st.warp >= 1 ? `×${st.warp.toLocaleString()}` : "×1";

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <div className="title">ABSOLUTESPACE · MISSION OPERATIONS CENTER</div>
          <button className="director-chip" onClick={() => setShowDirector(true)}
            title="Manage your Director identity & PIN">
            {conn.secured ? "🔒" : "🔓"} Director #{conn.playerId ?? "----"}
            {conn.playerName ? ` · ${conn.playerName}` : ""}
          </button>
        </div>
        <div className="meta">
          <div className="funds" title="Available funding">
            §{st ? Math.round(st.funds).toLocaleString() : "—"}M
            {st && st.budgetPenalty > 0 && (
              <span className="penalty" title={st.congressNote}>
                ⚠ −§{Math.round(st.budgetPenalty)}M next
              </span>
            )}
          </div>
          <div className={`date ${st?.paused ? "paused" : ""}`}>
            {st ? `MET DATE: ${st.date}` : "—"}
            {st?.paused ? "  [PAUSED]" : ""}
          </div>
          <div className="warp-controls">
            <button onClick={conn.warpDown} title="Slower">◄</button>
            <span className="warp-val">{warpLabel}</span>
            <button onClick={conn.warpUp} title="Faster">►</button>
            <button onClick={conn.togglePause} title="Pause/Resume">
              {st?.paused ? "▶ Resume" : "⏸ Pause"}
            </button>
          </div>
          <div>
            <span className={`conn-dot ${conn.connected ? "on" : "off"}`} />
            {conn.connected ? "LIVE" : "OFFLINE"}
          </div>
        </div>
      </header>

      {view === "command" && (
        <CommandCenter conn={conn} onOpenFacility={handleFacility} />
      )}
      {view === "builder" && <CraftBuilder onBack={() => setView("command")} />}
      {view === "operations" && (
        <Operations conn={conn} onBack={() => setView("command")}
          onGoToPad={() => setView("launchpad")} />
      )}
      {view === "launchpad" && (
        <LaunchPad conn={conn} onBack={() => setView("command")} />
      )}

      <footer className="app-footer">
        Multiplayer session · {st?.playersOnline ?? 0} controller(s) online
        {st?.playerNames?.length ? ` — ${st.playerNames.join(", ")}` : ""}
        &nbsp;·&nbsp; resize / move this window like any standard app
      </footer>

      {showDirector && <DirectorPanel conn={conn} onClose={() => setShowDirector(false)} />}

      {!conn.connected && (
        <div className="overlay">
          <div className="box">
            <div className="big">CONNECTING TO MISSION CONTROL…</div>
            <div className="sub">
              Establishing link to game server (backend on :8000).
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
