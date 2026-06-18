import { useEffect, useState } from "react";
import type { GameConnection } from "../useGameSocket";

interface Props {
  conn: GameConnection;
  onClose: () => void;
}

export function DirectorPanel({ conn, onClose }: Props) {
  const [name, setName] = useState(conn.playerName ?? "");
  const [pin, setPin] = useState("");
  const [pin2, setPin2] = useState("");
  const [claimId, setClaimId] = useState("");
  const [claimPin, setClaimPin] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => setName(conn.playerName ?? ""), [conn.playerName]);

  // pre-fill the claim field with the last-known director number
  useEffect(() => {
    try {
      const saved = localStorage.getItem("as_directorId");
      if (saved) setClaimId(saved);
    } catch {}
  }, []);

  // surface backend identity results
  useEffect(() => {
    if (!conn.identityResult) return;
    setMsg(conn.identityResult.ok ? "✓ Done." : `✗ ${conn.identityResult.error ?? "Failed."}`);
    if (conn.identityResult.ok) {
      setPin(""); setPin2(""); setClaimPin("");
    }
  }, [conn.identityResult]);

  const pinValid = /^\d{4,8}$/.test(pin) && pin === pin2;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dir-modal" onClick={(e) => e.stopPropagation()}>
        <div className="dir-head">
          <span>DIRECTOR IDENTITY</span>
          <button className="dir-x" onClick={onClose}>✕</button>
        </div>

        <div className="dir-id">
          <div className="dir-num">Director #{conn.playerId ?? "----"}</div>
          <div className={`dir-lock ${conn.secured ? "on" : ""}`}>
            {conn.secured ? "🔒 Secured" : "🔓 Unsecured"}
          </div>
        </div>

        {/* Display name */}
        <div className="dir-section">
          <label>Identifier (display name)</label>
          <div className="dir-row">
            <input value={name} maxLength={24} onChange={(e) => setName(e.target.value)} />
            <button className="btn primary sm"
              onClick={() => { if (name.trim()) conn.setName(name.trim()); }}>
              Save
            </button>
          </div>
        </div>

        {/* Secure with a PIN */}
        <div className="dir-section">
          <label>{conn.secured ? "Change PIN" : "Secure with a PIN"}</label>
          <div className="dir-warn">
            ⚠ Save your Director number <b>#{conn.playerId}</b> and PIN. The PIN
            cannot be recovered — you need both to resume this identity (and its
            fleet) later or on another device.
          </div>
          <div className="dir-row">
            <input type="password" inputMode="numeric" placeholder="PIN (4–8 digits)"
              value={pin} maxLength={8}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />
            <input type="password" inputMode="numeric" placeholder="Confirm PIN"
              value={pin2} maxLength={8}
              onChange={(e) => setPin2(e.target.value.replace(/\D/g, ""))} />
          </div>
          <label className="dir-ack">
            <input type="checkbox" checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)} />
            I have saved my Director number and PIN.
          </label>
          <button className="btn primary sm"
            disabled={!pinValid || !acknowledged}
            onClick={() => conn.setPin(pin)}>
            {conn.secured ? "Update PIN" : "Secure identity"}
          </button>
          {conn.secured && (
            <button className="btn sm ghost"
              onClick={() => { if (pin) conn.clearPin(pin); }}>
              Remove PIN (enter current PIN above)
            </button>
          )}
        </div>

        {/* Resume an existing director */}
        <div className="dir-section">
          <label>Resume a Director</label>
          <div className="dir-row">
            <input inputMode="numeric" placeholder="Director #"
              value={claimId} maxLength={5}
              onChange={(e) => setClaimId(e.target.value.replace(/\D/g, ""))} />
            <input type="password" inputMode="numeric" placeholder="PIN"
              value={claimPin} maxLength={8}
              onChange={(e) => setClaimPin(e.target.value.replace(/\D/g, ""))} />
            <button className="btn sm"
              onClick={() => { if (claimId) conn.claimDirector(claimId, claimPin); }}>
              Claim
            </button>
          </div>
          <div className="dir-hint">
            Switches this session to that Director (restores its missions). Secured
            Directors require the correct PIN.
          </div>
        </div>

        {msg && <div className="dir-msg">{msg}</div>}
      </div>
    </div>
  );
}
