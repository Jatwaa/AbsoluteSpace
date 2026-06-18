export type Urgency =
  | "CRITICAL"
  | "SOON"
  | "UPCOMING"
  | "NOMINAL"
  | "NONE";

export interface Attention {
  urgency: Urgency;
  label: string;
  countdown: string;
  time: number | null;
}

export interface Mission {
  name: string;
  origin: string;
  destination: string;
  phase: string;
  phaseId: string;
  isActive: boolean;
  crew: number;
  deltaV: number;
  fuelTons: number;
  status: string;
  departDate: string;
  arriveDate: string;
  attention: Attention;
}

export type ContractStatus =
  | "AVAILABLE"
  | "ACCEPTED"
  | "PLANNED"
  | "VEHICLE_ASSIGNED"
  | "READY"
  | "LAUNCHED";

export interface ChosenWindow {
  departTime: number;
  departDate: string;
  arriveDate: string;
  durationDays: number;
  dvTotal: number;
  quality: string;
}

export type Severity = "PASS" | "WARN" | "FAIL";

export interface DryCheck {
  name: string;
  severity: Severity;
  message: string;
  fix: string;
}

export interface DryRunResult {
  attempt: number;
  ready: boolean;
  warnings: number;
  fails: number;
  launchTime: number;
  launchDate: string;
  siteId: string;
  checks: DryCheck[];
}

export interface Issue {
  id: string;
  op: string;
  category: string;
  description: string;
  failureChance: number;
  correctionCost: number;
  correctionDays: number;
  corrected: boolean;
}

export interface OpLogEntry {
  op: string;
  label: string;
  cost: number;
  summary: string;
  note?: string;
  date: string;
}

export interface ActiveTask {
  id: string;
  kind: string;
  label: string;
  cost: number;
  durationDays: number;
  status: "PENDING" | "RUNNING";
  progress: number;       // 0..1 at the moment of the snapshot
  remainingDays: number;
  op: string | null;
  issueId: string | null;
}

export interface SlotConflict {
  withId: string;
  withTitle: string;
  withOwner: string;
  siteId: string;
}

export interface Contract {
  id: string;
  title: string;
  objective: string;
  description: string;
  origin: string;
  destination: string;
  requiredDeltaV: number;
  requiredCrew: number;
  payloadKeywords: string[];
  reward: number;
  source: string;
  status: ContractStatus;
  chosenWindow: ChosenWindow | null;
  craftName: string | null;
  launchSiteId: string | null;
  plannedLaunchTime: number | null;
  plannedLaunchDate: string | null;
  daysToWindow: number | null;
  windowMissed: boolean;
  designOk: boolean;
  dryRunCount: number;
  lastDryRun: DryRunResult | null;
  issues: Issue[];
  opsRun: string[];
  opLog: OpLogEntry[];
  vehicleWear: number;
  missionRisk: number;
  budget: number;
  spent: number;
  activeTask: ActiveTask | null;
  queue: ActiveTask[];
  conflict: SlotConflict | null;
  ownerId: string | null;
  ownerName: string | null;
  missionName: string | null;
  outcome: string | null;
}

export interface CraftSpec {
  name: string;
  stages: number;
  totalMass: number;
  totalMassTons: number;
  totalDeltaV: number;
  twr: number;
  crew: number;
  partNames: string[];
}

export interface GameStateMsg {
  type: "state";
  simTime: number;
  date: string;
  warp: number;
  warpIdx: number;
  paused: boolean;
  playersOnline: number;
  playerNames: string[];
  missionCount: number;
  criticalCount: number;
  missions: Mission[];
  funds: number;
  budgetPenalty: number;
  congressNote: string;
  contracts: Contract[];
  crafts: CraftSpec[];
}

export interface ChatMessage {
  id: number;
  author: string;
  role: string;
  text: string;
  date: string;
}

export interface ChatMsg {
  type: "chat";
  messages: ChatMessage[];
}

export interface WelcomeMsg {
  type: "welcome";
  playerId: string;
  name: string;
}

export type ServerMessage = GameStateMsg | ChatMsg | WelcomeMsg;
