interface Facility {
  id: string;
  label: string;
  sub: string;
  enabled: boolean;
  accent: string;
}

const FACILITIES: Facility[] = [
  { id: "BUILDER", label: "VEHICLE ASSEMBLY", sub: "Design & build craft", enabled: true, accent: "var(--accent)" },
  { id: "LAUNCHPAD", label: "LAUNCH PAD", sub: "Missions · dry runs · launch", enabled: true, accent: "var(--orange)" },
  { id: "MAP", label: "MISSION MAP", sub: "Solar-system view", enabled: true, accent: "var(--green)" },
  { id: "CONGRESS", label: "CONGRESS", sub: "Budget & funding", enabled: false, accent: "var(--warn)" },
  { id: "ASTRO", label: "ASTRONAUT CORPS", sub: "Crew roster & training", enabled: false, accent: "#d08020" },
  { id: "TECH", label: "TECHNOLOGIES", sub: "R&D tech tree", enabled: false, accent: "#9670c8" },
];

interface Props {
  onOpen: (id: string) => void;
}

export function Facilities({ onOpen }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">FACILITIES</div>
      <div className="panel-body">
        {FACILITIES.map((f) => (
          <div
            key={f.id}
            className={`facility ${f.enabled ? "" : "locked"}`}
            style={{ borderLeftColor: f.accent }}
            onClick={() => f.enabled && onOpen(f.id)}
          >
            <div className="f-label">{f.label}</div>
            <div className="f-sub">{f.sub}</div>
            {!f.enabled && <div className="f-lock">LOCKED</div>}
          </div>
        ))}
        <div className="facility-note">
          Locked facilities are placeholders for future expansion
          (Congress / Astronaut Corps / Technologies).
        </div>
      </div>
    </div>
  );
}
