// Craft assembly model + KSP-style staging computation (client-side, live).
//
// Convention requested: STAGE 1 is the FIRST part added (top of the stack);
// stage numbers increase DOWNWARD. Decouplers define stage boundaries.
// Physically the bottom-most stage fires first, carrying everything above it
// (lower stage numbers / payload) as mass — so ΔV is summed correctly while
// the labels read 1..N from the top.

export const G0 = 9.80665;

export interface ApiModule {
  type: "module";
  name: string;
  moduleType: string;
  moduleTypeId:
    | "COMMAND"
    | "ENGINE"
    | "FUEL_TANK"
    | "PAYLOAD"
    | "SOLAR_PANEL"
    | "COMMS"
    | "DECOUPLER";
  dryMass: number;
  thrust: number;
  isp: number;
  fuelCapacity: number;
  lifeSupportMass: number;
  powerOutput: number;
  powerDraw: number;
  crew: number;
  description: string;
}

export interface ApiBranch {
  type: "branch";
  label: string;
  expanded: boolean;
  children: ApiNode[];
}

export type ApiNode = ApiModule | ApiBranch;

// A part instance in the stack (module + unique id for React keys / selection).
export interface Part {
  uid: number;
  mod: ApiModule;
}

export interface Stage {
  number: number;        // 1 = top (first added), increasing downward
  parts: Part[];         // non-decoupler parts in this group
  dryMass: number;       // kg
  propellant: number;    // kg
  wetMass: number;       // kg
  thrust: number;        // N (vacuum)
  ispEff: number;        // s (mass-flow weighted)
  deltaV: number;        // m/s (Tsiolkovsky, with everything above as payload)
  engines: number;
  firesFirst: boolean;   // bottom-most stage that has engines
}

export interface CraftStats {
  stages: Stage[];
  totalMass: number;     // kg
  dryMass: number;       // kg
  propellant: number;    // kg
  totalDeltaV: number;   // m/s
  launchThrust: number;  // N (bottom firing stage)
  twr: number;           // launch thrust-to-weight (1 g)
  crew: number;
}

const PROPULSIVE = (m: ApiModule) => m.moduleTypeId !== "DECOUPLER";

function partMass(m: ApiModule): number {
  return m.dryMass + m.fuelCapacity + m.lifeSupportMass * m.crew;
}

// Split the flat part list into stage groups at decoupler boundaries.
// Decouplers are boundaries only and are excluded from group mass (matches
// the backend Spacecraft.compute_stages simplification).
export function computeStats(parts: Part[]): CraftStats {
  const groups: Part[][] = [];
  let current: Part[] = [];
  for (const p of parts) {
    if (p.mod.moduleTypeId === "DECOUPLER") {
      if (current.length) groups.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) groups.push(current);

  // Per-group raw aggregates
  const raw = groups.map((g) => {
    const dryMass = g.reduce((s, p) => s + p.mod.dryMass + p.mod.lifeSupportMass * p.mod.crew, 0);
    const propellant = g.reduce((s, p) => s + p.mod.fuelCapacity, 0);
    const thrust = g.reduce((s, p) => s + p.mod.thrust, 0);
    const engines = g.filter((p) => p.mod.moduleTypeId === "ENGINE").length;
    // mass-flow weighted Isp
    const mdot = g.reduce(
      (s, p) => s + (p.mod.isp > 0 ? p.mod.thrust / (p.mod.isp * G0) : 0),
      0
    );
    const ispEff = mdot > 0 ? thrust / (mdot * G0) : 0;
    return { dryMass, propellant, thrust, engines, ispEff };
  });

  const wetOf = (i: number) => raw[i].dryMass + raw[i].propellant;

  // Bottom-most stage with engines fires first.
  let firstFireIdx = -1;
  for (let i = raw.length - 1; i >= 0; i--) {
    if (raw[i].engines > 0) {
      firstFireIdx = i;
      break;
    }
  }

  const stages: Stage[] = groups.map((g, i) => {
    // "above" = everything toward the nose (lower index) — rides as payload.
    let aboveWet = 0;
    for (let j = 0; j < i; j++) aboveWet += wetOf(j);

    const m0 = wetOf(i) + aboveWet;
    const mf = raw[i].dryMass + aboveWet;
    let deltaV = 0;
    if (raw[i].engines > 0 && raw[i].ispEff > 0 && mf > 0 && m0 > mf) {
      deltaV = raw[i].ispEff * G0 * Math.log(m0 / mf);
    }
    return {
      number: i + 1, // Stage 1 at top
      parts: g,
      dryMass: raw[i].dryMass,
      propellant: raw[i].propellant,
      wetMass: wetOf(i),
      thrust: raw[i].thrust,
      ispEff: raw[i].ispEff,
      deltaV,
      engines: raw[i].engines,
      firesFirst: i === firstFireIdx,
    };
  });

  const totalMass = parts.filter((p) => PROPULSIVE(p.mod)).reduce((s, p) => s + partMass(p.mod), 0);
  const dryMass = parts.filter((p) => PROPULSIVE(p.mod)).reduce((s, p) => s + p.mod.dryMass + p.mod.lifeSupportMass * p.mod.crew, 0);
  const propellant = parts.reduce((s, p) => s + p.mod.fuelCapacity, 0);
  const totalDeltaV = stages.reduce((s, st) => s + st.deltaV, 0);
  const launchThrust = firstFireIdx >= 0 ? raw[firstFireIdx].thrust : 0;
  const twr = totalMass > 0 ? launchThrust / (totalMass * 9.81) : 0;
  const crew = parts.reduce((s, p) => s + p.mod.crew, 0);

  return { stages, totalMass, dryMass, propellant, totalDeltaV, launchThrust, twr, crew };
}

// ── helpers ──────────────────────────────────────────────────────────────────

export function moduleKeyStat(m: ApiModule): string {
  if (m.thrust > 0 && m.isp > 0) {
    if (m.thrust < 1000) return `${m.thrust.toFixed(0)} N · ${m.isp}s`;
    if (m.thrust < 1_000_000) return `${(m.thrust / 1000).toFixed(0)} kN · ${m.isp}s`;
    return `${(m.thrust / 1000).toFixed(0)} kN`;
  }
  if (m.fuelCapacity > 0) {
    return m.fuelCapacity >= 1000
      ? `${(m.fuelCapacity / 1000).toFixed(1)} t prop`
      : `${m.fuelCapacity.toFixed(0)} kg prop`;
  }
  if (m.powerOutput > 0) return `${(m.powerOutput / 1000).toFixed(1)} kW`;
  if (m.crew > 0) return `${m.crew} crew`;
  return `${m.dryMass} kg`;
}

export const MODULE_COLORS: Record<string, string> = {
  COMMAND: "#2d8250",
  ENGINE: "#b44828",
  FUEL_TANK: "#2d5896",
  PAYLOAD: "#6e37a0",
  SOLAR_PANEL: "#9b8723",
  COMMS: "#238394",
  DECOUPLER: "#c88c28",
};

export function agencyOf(desc: string): string {
  if (desc.startsWith("[")) {
    const end = desc.indexOf("]");
    if (end > 0) return desc.slice(1, end).split("/")[0].trim();
  }
  return "Generic";
}
