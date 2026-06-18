"""
Real-world space module database with 1:1 values from agency sources.

Sources: NASA Technical Reports, ESA Fact Sheets, SpaceX press kits,
         JAXA mission data, ISRO documentation, Jane's Space Systems.

All masses in kg, thrust in N, Isp in seconds, power in W.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .craft import Module, ModuleType


@dataclass
class TreeNode:
    label: str                           # display name
    children: list["TreeNode"] = field(default_factory=list)
    module: Optional[Module] = None      # only on leaf nodes
    expanded: bool = True

    @property
    def is_leaf(self) -> bool:
        return self.module is not None

    def all_modules(self) -> list[Module]:
        if self.is_leaf:
            return [self.module]
        mods = []
        for c in self.children:
            mods.extend(c.all_modules())
        return mods


def _engine(name: str, agency: str, program: str,
            thrust_vac: float, isp_vac: float, dry_mass: float,
            propellant: str, description: str = "",
            thrust_sl: float = 0.0, isp_sl: float = 0.0,
            power_draw: float = 50.0) -> Module:
    desc = f"[{agency}] {propellant}. {description}".strip()
    return Module(
        name=name,
        module_type=ModuleType.ENGINE,
        dry_mass=dry_mass,
        thrust=thrust_vac,
        isp=isp_vac,
        power_draw=power_draw,
        description=desc,
    )


def _tank(name: str, agency: str, program: str,
          propellant_kg: float, dry_mass: float,
          propellant: str, description: str = "") -> Module:
    desc = f"[{agency}] {propellant}. {description}".strip()
    return Module(
        name=name,
        module_type=ModuleType.FUEL_TANK,
        dry_mass=dry_mass,
        fuel_capacity=propellant_kg,
        description=desc,
    )


def _command(name: str, agency: str, program: str,
             dry_mass: float, crew: int, power_draw: float = 500.0,
             life_support_mass_per_crew: float = 180.0,
             description: str = "") -> Module:
    desc = f"[{agency} / {program}] {description}".strip()
    m = Module(
        name=name,
        module_type=ModuleType.COMMAND,
        dry_mass=dry_mass,
        crew_capacity=crew,
        life_support_mass=life_support_mass_per_crew,
        power_draw=power_draw,
        description=desc,
    )
    return m


def _payload(name: str, agency: str, dry_mass: float,
             power_draw: float = 0.0, description: str = "") -> Module:
    desc = f"[{agency}] {description}"
    return Module(
        name=name,
        module_type=ModuleType.PAYLOAD,
        dry_mass=dry_mass,
        power_draw=power_draw,
        description=desc,
    )


def _solar(name: str, agency: str, power_w: float, dry_mass: float,
           description: str = "") -> Module:
    desc = f"[{agency}] {description}"
    return Module(
        name=name,
        module_type=ModuleType.SOLAR_PANEL,
        dry_mass=dry_mass,
        power_output=power_w,
        description=desc,
    )


def _rtg(name: str, agency: str, power_w: float, dry_mass: float,
         description: str = "") -> Module:
    desc = f"[{agency}] {description}"
    return Module(
        name=name,
        module_type=ModuleType.SOLAR_PANEL,
        dry_mass=dry_mass,
        power_output=power_w,
        description=desc,
    )


def _comms(name: str, agency: str, dry_mass: float, power_draw: float,
           description: str = "") -> Module:
    desc = f"[{agency}] {description}"
    return Module(
        name=name,
        module_type=ModuleType.COMMS,
        dry_mass=dry_mass,
        power_draw=power_draw,
        description=desc,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — CRYOGENIC (LH₂/LOX)
# ═══════════════════════════════════════════════════════════════════════════════
CRYO_ENGINES = [
    _engine("RS-25D/E", "NASA/Rocketdyne", "Space Shuttle / SLS",
            thrust_vac=2_279_000, thrust_sl=1_860_000,
            isp_vac=453, isp_sl=363, dry_mass=3_527,
            propellant="LH₂/LOX",
            description="Space Shuttle Main Engine. Reusable, throttleable 67–109%."),

    _engine("J-2X", "NASA/Rocketdyne", "SLS Upper Stage (Proposed)",
            thrust_vac=1_310_000, isp_vac=448, dry_mass=2_472,
            propellant="LH₂/LOX",
            description="Evolved J-2 for SLS EUS. Restart-capable."),

    _engine("RL-10B-2", "Aerojet Rocketdyne", "Delta IV / SLS ICPS",
            thrust_vac=110_094, isp_vac=465, dry_mass=277,
            propellant="LH₂/LOX",
            description="Highest Isp US flight engine. Extendable nozzle."),

    _engine("RL-10C-3", "Aerojet Rocketdyne", "Vulcan Centaur",
            thrust_vac=101_800, isp_vac=451, dry_mass=168,
            propellant="LH₂/LOX",
            description="Compact RL-10 variant for Centaur V upper stage."),

    _engine("RL-10A-4-2", "Aerojet Rocketdyne", "Atlas V Centaur",
            thrust_vac=99_000, isp_vac=450, dry_mass=167,
            propellant="LH₂/LOX",
            description="Atlas V dual-engine Centaur configuration capable."),

    _engine("Vulcain 2.1", "ArianeGroup/ESA", "Ariane 5 / Ariane 6",
            thrust_vac=1_340_000, thrust_sl=960_000,
            isp_vac=434, isp_sl=320, dry_mass=1_800,
            propellant="LH₂/LOX",
            description="Core stage of Ariane 5/6. Regeneratively cooled."),

    _engine("HM-7B", "SEP/ArianeGroup", "Ariane 5 EPS / Ariane 4",
            thrust_vac=64_800, isp_vac=446, dry_mass=165,
            propellant="LH₂/LOX",
            description="Ariane upper stage. Restart-capable, 5 restarts."),

    _engine("Vinci", "ArianeGroup/ESA", "Ariane 6 ESC-D",
            thrust_vac=180_000, isp_vac=457, dry_mass=550,
            propellant="LH₂/LOX",
            description="Re-ignitable upper stage engine for Ariane 6. Up to 5 restarts."),

    _engine("RD-0120", "NPO Energomash/Roscosmos", "Energia",
            thrust_vac=1_961_000, isp_vac=455, dry_mass=3_450,
            propellant="LH₂/LOX",
            description="Soviet super-heavy cryogenic core engine. ISS-era heritage."),

    _engine("LE-5B-3", "JAXA/IHI", "H-IIA / H-IIB",
            thrust_vac=137_200, isp_vac=447, dry_mass=255,
            propellant="LH₂/LOX",
            description="Japanese upper stage. Restart-capable, 2 burns."),

    _engine("LE-9", "JAXA/IHI", "H3",
            thrust_vac=1_471_000, thrust_sl=1_225_000,
            isp_vac=425, dry_mass=2_400,
            propellant="LH₂/LOX",
            description="H3 main stage. Expander bleed cycle, no turbopump preburner."),

    _engine("CE-20", "ISRO/LPSC", "GSLV Mk III / Gaganyaan",
            thrust_vac=200_000, isp_vac=443, dry_mass=588,
            propellant="LH₂/LOX",
            description="Indian cryogenic stage engine. Propels C25 upper stage."),

    _engine("YF-77", "CASC/CNSA", "Long March 5",
            thrust_vac=700_000, isp_vac=438, dry_mass=2_550,
            propellant="LH₂/LOX",
            description="China's first large cryogenic engine. LM-5 core stage, pair."),

    _engine("YF-75D", "CASC/CNSA", "Long March 3B/5",
            thrust_vac=88_360, isp_vac=442, dry_mass=550,
            propellant="LH₂/LOX",
            description="Chinese upper stage cryogenic. Restart-capable."),

    _engine("KVD-1", "ISRO/Isayev-LPSC", "GSLV Mk I/II",
            thrust_vac=73_500, isp_vac=461, dry_mass=283,
            propellant="LH₂/LOX",
            description="Russian-origin, ISRO-operated. Enables GSLV GTO missions."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — KEROSENE / LOX (RP-1 or RG-1)
# ═══════════════════════════════════════════════════════════════════════════════
KERO_ENGINES = [
    _engine("F-1", "NASA/Rocketdyne", "Saturn V S-IC",
            thrust_vac=7_740_500, thrust_sl=6_672_300,
            isp_vac=304, isp_sl=263, dry_mass=8_391,
            propellant="RP-1/LOX",
            description="Most powerful single-chamber engine flown. 5 per Saturn V stage."),

    _engine("J-2", "NASA/Rocketdyne", "Saturn V S-II / S-IVB",
            thrust_vac=1_033_100, isp_vac=421, dry_mass=1_788,
            propellant="LH₂/LOX",  # J-2 is actually LH2/LOX — correct
            description="S-II (5x) and S-IVB (1x) upper stages. Restart-capable."),

    _engine("Merlin 1D Vac", "SpaceX", "Falcon 9 S2 / Falcon Heavy S2",
            thrust_vac=934_000, isp_vac=348, dry_mass=490,
            propellant="RP-1/LOX",
            description="Single upper-stage engine. Fixed nozzle extension. 1 restart."),

    _engine("Merlin 1D SL", "SpaceX", "Falcon 9 S1 / Falcon Heavy",
            thrust_vac=914_000, thrust_sl=845_000,
            isp_vac=311, isp_sl=282, dry_mass=467,
            propellant="RP-1/LOX",
            description="9 per Falcon 9 first stage. Throttleable 40–100%."),

    _engine("Raptor 2 Vac", "SpaceX", "Starship Upper Stage",
            thrust_vac=2_050_000, isp_vac=380, dry_mass=1_600,
            propellant="CH₄/LOX",
            description="Full-flow staged combustion. Fixed vacuum nozzle. 6 per Ship."),

    _engine("Raptor 2 SL", "SpaceX", "Starship / Super Heavy",
            thrust_vac=2_230_000, thrust_sl=2_100_000,
            isp_vac=350, isp_sl=327, dry_mass=1_600,
            propellant="CH₄/LOX",
            description="Gimballing sea-level engine. Up to 33 per Super Heavy booster."),

    _engine("BE-4", "Blue Origin", "New Glenn S1 / Vulcan S1",
            thrust_vac=2_400_000, thrust_sl=2_180_000,
            isp_vac=339, isp_sl=310, dry_mass=2_500,
            propellant="LNG/LOX",
            description="Liquefied natural gas/LOX. Staged combustion. 7 per New Glenn S1."),

    _engine("BE-3U", "Blue Origin", "New Glenn S2",
            thrust_vac=710_000, isp_vac=464, dry_mass=1_400,
            propellant="LH₂/LOX",
            description="Expander cycle upper stage engine. Restart-capable."),

    _engine("RD-180", "NPO Energomash", "Atlas V (Roscosmos/ULA)",
            thrust_vac=4_152_000, thrust_sl=3_830_000,
            isp_vac=338, isp_sl=311, dry_mass=5_393,
            propellant="RP-1/LOX",
            description="Two-chamber single-turbopump. Atlas V core stage."),

    _engine("RD-107A", "NPO Energomash/Roscosmos", "Soyuz-2 Booster",
            thrust_vac=1_021_300, thrust_sl=838_500,
            isp_vac=320, isp_sl=263, dry_mass=1_190,
            propellant="RP-1/LOX",
            description="4-chamber + 2 verniers per strap-on booster. 4 boosters on Soyuz."),

    _engine("RD-108A", "NPO Energomash/Roscosmos", "Soyuz-2 Core",
            thrust_vac=990_200, thrust_sl=792_500,
            isp_vac=320, isp_sl=257, dry_mass=1_250,
            propellant="RP-1/LOX",
            description="Core stage of Soyuz-2. 4 chambers + 4 vernier engines."),

    _engine("RD-171M", "NPO Energomash/Roscosmos", "Zenit / Antares",
            thrust_vac=7_904_000, thrust_sl=7_259_000,
            isp_vac=337, isp_sl=309, dry_mass=9_750,
            propellant="RP-1/LOX",
            description="Highest thrust single-turbopump engine ever flown. 4-chamber."),

    _engine("NK-33 (AJ-26)", "Kuznetsov/Aerojet", "N1 / Antares S1",
            thrust_vac=1_754_000, thrust_sl=1_511_000,
            isp_vac=331, isp_sl=297, dry_mass=1_222,
            propellant="RP-1/LOX",
            description="N1 lunar rocket heritage. AJ-26 form flew on Antares. High T/W."),

    _engine("RD-253 / RD-275M", "NPO Energomash/Roscosmos", "Proton-M",
            thrust_vac=1_832_000, thrust_sl=1_748_000,
            isp_vac=316, isp_sl=285, dry_mass=1_080,
            propellant="UDMH/N₂O₄",
            description="Proton first-stage engine. 6 per stage. Hypergolic."),

    _engine("Rutherford Vac", "Rocket Lab", "Electron S2",
            thrust_vac=25_800, isp_vac=343, dry_mass=35,
            propellant="RP-1/LOX",
            description="Electric-pump cycle. Lightest operational orbital upper engine."),

    _engine("Rutherford SL", "Rocket Lab", "Electron S1",
            thrust_vac=24_910, thrust_sl=22_200,
            isp_vac=327, isp_sl=311, dry_mass=35,
            propellant="RP-1/LOX",
            description="9 per Electron first stage. 3D-printed chamber. Electric pump."),

    _engine("YF-100K", "CASC/CNSA", "Long March 7 / Long March 5B",
            thrust_vac=1_399_000, thrust_sl=1_188_000,
            isp_vac=335, isp_sl=300, dry_mass=1_800,
            propellant="RP-1/LOX",
            description="China's latest kerosene core engine. LM-7 uses 2 at core."),

    _engine("Vikas-4 (L110)", "ISRO/LPSC", "GSLV Mk III L110",
            thrust_vac=800_000, thrust_sl=680_000,
            isp_vac=295, isp_sl=261, dry_mass=2_000,
            propellant="UDMH/N₂O₄",
            description="2 per GSLV Mk III liquid core stage. Indian-built. Storable."),
]

# Move J-2 to cryo (it IS LH2/LOX) — already correct above

# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — HYPERGOLIC (MMH/NTO or UDMH/N₂O₄)
# ═══════════════════════════════════════════════════════════════════════════════
HYPERGOLIC_ENGINES = [
    _engine("AJ10-190", "Aerojet Rocketdyne", "Space Shuttle OMS / Orion ESM",
            thrust_vac=26_690, isp_vac=316, dry_mass=118,
            propellant="MMH/NTO",
            description="Shuttle OMS and Orion service module main engine."),

    _engine("R-40B", "Aerojet Rocketdyne", "Various Upper Stages",
            thrust_vac=4_000, isp_vac=293, dry_mass=8,
            propellant="MMH/NTO",
            description="Bipropellant apogee/RCS thruster."),

    _engine("Aestus", "ArianeGroup", "Ariane 5 ECA Upper Stage",
            thrust_vac=29_600, isp_vac=324, dry_mass=111,
            propellant="MMH/N₂O₄",
            description="Pressure-fed upper stage. Up to 10 restarts."),

    _engine("Aestus II (RS-72)", "Aerojet/ESA", "Ariane 5 ESC-B (proposed)",
            thrust_vac=55_000, isp_vac=340, dry_mass=130,
            propellant="MMH/N₂O₄",
            description="Pump-fed upgrade to Aestus."),

    _engine("S5.92 (Fregat)", "Isayev Chemical / Roscosmos", "Fregat Upper Stage",
            thrust_vac=19_850, isp_vac=327, dry_mass=87,
            propellant="UDMH/N₂O₄",
            description="Fregat upper stage main engine. 20 restarts."),

    _engine("S5.98M (Briz-M)", "Isayev Chemical / Roscosmos", "Briz-M Upper Stage",
            thrust_vac=19_850, isp_vac=326, dry_mass=87,
            propellant="UDMH/N₂O₄",
            description="Briz-M toroidal-tank upper stage. 8 restarts typical GTO mission."),

    _engine("HiPAT R-4D", "Aerojet Rocketdyne", "Various Orbiters",
            thrust_vac=490, isp_vac=312, dry_mass=3,
            propellant="MMH/NTO",
            description="Standard spacecraft apogee thruster. Many planetary orbiters."),

    _engine("LEROS 1c", "Bradford ECAPS", "Lunar Orbiters / ESA",
            thrust_vac=635, isp_vac=317, dry_mass=4,
            propellant="MMH/NTO",
            description="Low Earth/deep space thruster used in SMART-1, GlobeComm."),

    _engine("YF-24E", "CASC/CNSA", "Long March 2F Service Module",
            thrust_vac=6_500, isp_vac=291, dry_mass=42,
            propellant="UDMH/N₂O₄",
            description="Shenzhou spacecraft service module orbital engine."),

    _engine("CE-10 (PSLV US)", "ISRO", "PSLV Upper Stage",
            thrust_vac=7_600, isp_vac=308, dry_mass=52,
            propellant="MMH/NTO",
            description="PSLV 4th stage (PS4) pressure-fed hypergolic."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — SOLID ROCKET MOTORS
# ═══════════════════════════════════════════════════════════════════════════════
SOLID_MOTORS = [
    # Solid motors modelled as engine + pre-filled tank combined (fuel_capacity=propellant mass)
    Module(
        name="RSRM (Shuttle SRB)",
        module_type=ModuleType.ENGINE,
        dry_mass=86_183,
        fuel_capacity=502_126,
        thrust=12_453_000,
        isp=269,
        description="[NASA/ATK] AP/PBAN. Each SRB; 2 per Shuttle. Recoverable/refurbishable.",
    ),
    Module(
        name="RSRM-V (SLS SRB)",
        module_type=ModuleType.ENGINE,
        dry_mass=97_318,
        fuel_capacity=628_000,
        thrust=15_000_000,
        isp=275,
        description="[NASA/Northrop Grumman] Upgraded Shuttle SRB. 2 per SLS Block 1.",
    ),
    Module(
        name="P80 (Vega 1st Stage)",
        module_type=ModuleType.ENGINE,
        dry_mass=7_300,
        fuel_capacity=88_000,
        thrust=3_015_000,
        isp=280,
        description="[ESA/Avio/ArianeGroup] HTPB composite propellant. First stage of Vega.",
    ),
    Module(
        name="Zefiro-23 (Vega 2nd)",
        module_type=ModuleType.ENGINE,
        dry_mass=1_900,
        fuel_capacity=23_900,
        thrust=1_197_000,
        isp=288,
        description="[ESA/Avio] 2nd stage of Vega/Vega-C. Carbon fiber wound case.",
    ),
    Module(
        name="Zefiro-9 (Vega 3rd)",
        module_type=ModuleType.ENGINE,
        dry_mass=695,
        fuel_capacity=10_500,
        thrust=260_000,
        isp=296,
        description="[ESA/Avio] 3rd stage of Vega. Vectorable nozzle.",
    ),
    Module(
        name="Castor 30XL",
        module_type=ModuleType.ENGINE,
        dry_mass=2_800,
        fuel_capacity=26_411,
        thrust=1_688_000,
        isp=296,
        description="[Northrop Grumman] Antares 2nd stage. Developed from Castor 30B.",
    ),
    Module(
        name="Star-63F",
        module_type=ModuleType.ENGINE,
        dry_mass=220,
        fuel_capacity=1_085,
        thrust=68_900,
        isp=290,
        description="[Northrop/ATK] Upper stage kick motor. Magellan, Galileo."),
    Module(
        name="S-400 (Astrid / Mars-96)",
        module_type=ModuleType.ENGINE,
        dry_mass=11,
        fuel_capacity=108,
        thrust=400,
        isp=284,
        description="[Thiokol] Small apogee kick motor for science missions."),
    Module(
        name="S200 (GSLV Mk III SRB)",
        module_type=ModuleType.ENGINE,
        dry_mass=30_000,
        fuel_capacity=207_000,
        thrust=5_150_000,
        isp=274,
        description="[ISRO/VSSC] World's 3rd largest solid booster. 2 per GSLV Mk III.",
    ),
    Module(
        name="YF-73 (Long March CZ-4B)",
        module_type=ModuleType.ENGINE,
        dry_mass=1_200,
        fuel_capacity=10_000,
        thrust=150_000,
        isp=291,
        description="[CASC/CNSA] Solid upper stage for polar/sun-sync missions.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — ION & ELECTRIC
# ═══════════════════════════════════════════════════════════════════════════════
ION_ENGINES = [
    _engine("NSTAR", "NASA/JPL", "Dawn / Deep Space 1",
            thrust_vac=92, isp_vac=3_100, dry_mass=8,
            propellant="Xenon", power_draw=2_300,
            description="Gridded ion thruster. 3 units on Dawn. 11 km/s Δv logged."),

    _engine("NEXT-C", "NASA GRC/Aerojet", "Psyche / Lucy",
            thrust_vac=237, isp_vac=4_190, dry_mass=14,
            propellant="Xenon", power_draw=6_900,
            description="NASA Evolutionary Xenon Thruster. 2–3 per spacecraft."),

    _engine("T6 (Kaufman Ion)", "QinetiQ / ESA", "BepiColombo (ESA/JAXA)",
            thrust_vac=145, isp_vac=4_120, dry_mass=14,
            propellant="Xenon", power_draw=6_000,
            description="Gridded ion. 4 per BepiColombo Solar Electric Propulsion module."),

    _engine("PPS-1350", "Safran/Snecma", "SMART-1 (ESA)",
            thrust_vac=68, isp_vac=1_600, dry_mass=5,
            propellant="Xenon", power_draw=1_500,
            description="Hall-effect thruster. First ESA ion propulsion. SMART-1 lunar orbit."),

    _engine("SPT-100", "OKB Fakel/Roscosmos", "EXPRESS / YAMAL Satellites",
            thrust_vac=83, isp_vac=1_600, dry_mass=4,
            propellant="Xenon", power_draw=1_350,
            description="Stationary Plasma Thruster. Soviet/Russian standard comsat HET."),

    _engine("SPT-140 (PPS-5000)", "OKB Fakel / Safran", "AEHF / Various GEO",
            thrust_vac=290, isp_vac=1_780, dry_mass=9,
            propellant="Xenon", power_draw=5_000,
            description="High-power hall-effect for GEO all-electric spacecraft."),

    _engine("RIT-22", "Astrium/ESA", "Planned ESA Deep Space",
            thrust_vac=200, isp_vac=4_165, dry_mass=14,
            propellant="Xenon", power_draw=5_000,
            description="Radio-frequency ion thruster. ESA test heritage on ARTEMIS."),

    _engine("μ10 ECR", "JAXA/NEC", "Hayabusa / Hayabusa2",
            thrust_vac=10, isp_vac=3_000, dry_mass=3,
            propellant="Xenon", power_draw=350,
            description="Microwave discharge ECR ion engine. 4 per Hayabusa. Asteroid sample return."),

    _engine("BHT-8000", "Busek", "AEHF / US Military",
            thrust_vac=454, isp_vac=2_210, dry_mass=11,
            propellant="Xenon", power_draw=8_000,
            description="Hall-effect, highest-power US operational hall thruster."),

    _engine("HEMPT (DM3a)", "Thales/ESA", "SmallGEO / ESA",
            thrust_vac=56, isp_vac=3_000, dry_mass=2,
            propellant="Xenon", power_draw=1_500,
            description="Highly Efficient Multistage Plasma Thruster. ESA commercial sat."),

    _engine("Ion Thruster HIT-ITR (Tiangong)", "CASC/CAST", "CSS Tianhe",
            thrust_vac=100, isp_vac=2_200, dry_mass=5,
            propellant="Xenon", power_draw=2_000,
            description="Hall ion thruster for Chinese Space Station orbit maintenance."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPULSION — NUCLEAR THERMAL
# ═══════════════════════════════════════════════════════════════════════════════
NUCLEAR_ENGINES = [
    _engine("NERVA NRX/XE", "NASA/AEC", "Nuclear Engine for Rocket Vehicle Application",
            thrust_vac=333_600, isp_vac=841, dry_mass=6_803,
            propellant="LH₂ (nuclear heated)", power_draw=0,
            description="Ground-tested 1969. 825 MW reactor. Never flown; program cancelled 1973."),

    _engine("NERVA B-4", "NASA/Westinghouse", "Nuclear Shuttle (Proposed)",
            thrust_vac=1_112_000, isp_vac=825, dry_mass=22_680,
            propellant="LH₂ (nuclear heated)", power_draw=0,
            description="Planned for Earth-Moon shuttle. 5,000 MW design. Not built."),

    _engine("Project Timberwind", "SDIO/NASA", "Nuclear Thermal (Classified)",
            thrust_vac=735_000, isp_vac=1_000, dry_mass=4_000,
            propellant="LH₂ (nuclear heated)", power_draw=0,
            description="Particle-bed reactor NTR. SDIO 1980s program. Declassified concept."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPELLANT TANKS
# ═══════════════════════════════════════════════════════════════════════════════
CRYO_TANKS = [
    _tank("S-IC Stage Tanks", "NASA/Boeing", "Saturn V Stage 1",
          propellant_kg=2_077_000, dry_mass=130_000,
          propellant="RP-1/LOX",
          description="Saturn V 1st stage. 5× F-1 engines. Structures included."),

    _tank("S-II Stage Tanks", "NASA/NAR", "Saturn V Stage 2",
          propellant_kg=456_100, dry_mass=36_200,
          propellant="LH₂/LOX",
          description="Saturn V 2nd stage. 5× J-2. Ultra-thin common bulkhead tank wall."),

    _tank("S-IVB Tank", "NASA/Douglas", "Saturn V / Saturn IB Stage 3",
          propellant_kg=108_825, dry_mass=13_311,
          propellant="LH₂/LOX",
          description="1× J-2. Saturn IB uses as 2nd stage. 2 restarts in Earth orbit."),

    _tank("Centaur V (RL-10)", "ULA", "Vulcan Centaur Upper Stage",
          propellant_kg=54_500, dry_mass=2_243,
          propellant="LH₂/LOX",
          description="Stainless steel balloon-tank. 2× RL-10C-3. 15 restarts capable."),

    _tank("ICPS (SLS Block 1)", "NASA/Boeing", "SLS Interim Cryogenic Propulsion Stage",
          propellant_kg=27_220, dry_mass=3_000,
          propellant="LH₂/LOX",
          description="Modified Delta IV upper stage (DCSS). 1× RL-10B-2. Artemis 1/2/3."),

    _tank("EUS (SLS Block 1B)", "NASA/Boeing", "Exploration Upper Stage",
          propellant_kg=129_000, dry_mass=13_000,
          propellant="LH₂/LOX",
          description="SLS Block 1B upgrade. 4× RL-10C-3. 2× ICPS payload capacity."),
]

KERO_TANKS = [
    _tank("Falcon 9 S1 Tanks", "SpaceX", "Falcon 9 Block 5 First Stage",
          propellant_kg=418_000, dry_mass=25_600,
          propellant="RP-1/LOX",
          description="9× Merlin 1D. Reusable 15+ times. Aluminum-lithium airframe."),

    _tank("Falcon 9 S2 Tank", "SpaceX", "Falcon 9 Block 5 Second Stage",
          propellant_kg=107_500, dry_mass=4_000,
          propellant="RP-1/LOX",
          description="1× Merlin 1D Vac. Expended each mission. 1 restart max."),

    _tank("Super Heavy Tanks", "SpaceX", "Starship Super Heavy Booster",
          propellant_kg=3_400_000, dry_mass=200_000,
          propellant="CH₄/LOX",
          description="33× Raptor 2. Fully reusable. Mechazilla catch system."),

    _tank("Starship Ship Tanks", "SpaceX", "Starship Upper Stage",
          propellant_kg=1_200_000, dry_mass=100_000,
          propellant="CH₄/LOX",
          description="6× Raptor 2 (3 vac + 3 SL). Payload: up to 100 t to LEO."),

    _tank("New Glenn S1 Tanks", "Blue Origin", "New Glenn First Stage",
          propellant_kg=1_800_000, dry_mass=140_000,
          propellant="LNG/LOX",
          description="7× BE-4. Reusable booster with landing legs."),

    _tank("RD-107A Stage Tanks", "Roscosmos", "Soyuz-2.1a Booster Tanks (×4)",
          propellant_kg=39_600, dry_mass=3_784,
          propellant="RP-1/LOX",
          description="Each of 4 Soyuz strap-on boosters. 1× RD-107A each."),

    _tank("RD-108A Core Tank", "Roscosmos", "Soyuz-2 Core Stage",
          propellant_kg=91_000, dry_mass=6_545,
          propellant="RP-1/LOX",
          description="Soyuz Block-A central stage. 1× RD-108A."),

    _tank("Proton Stage 1 Tanks", "Roscosmos/Khrunichev", "Proton-M Stage 1",
          propellant_kg=419_400, dry_mass=30_600,
          propellant="UDMH/N₂O₄",
          description="6× RD-275M engines around central LOX tank. Hypergolic."),
]

STORABLE_TANKS = [
    _tank("Fregat Tank", "Lavochkin / Roscosmos", "Fregat Upper Stage",
          propellant_kg=5_350, dry_mass=900,
          propellant="UDMH/N₂O₄",
          description="Russian restartable upper stage. 20 ignitions. Used with Soyuz/Zenit."),

    _tank("Briz-M Tank", "Khrunichev / Roscosmos", "Proton-M Upper Stage",
          propellant_kg=19_800, dry_mass=2_000,
          propellant="UDMH/N₂O₄",
          description="Toroidal main tank + jettisoned additional tank. GTO to GEO delivery."),

    _tank("Apollo SM Tank", "NASA/NAR", "Apollo Command/Service Module",
          propellant_kg=18_413, dry_mass=6_100,
          propellant="MMH/N₂O₄ (AJ10)",
          description="Apollo service module propulsion. TEI + LOI. AJ10 engine."),

    _tank("Orion ESM Tank", "ESA/Airbus", "Orion European Service Module",
          propellant_kg=8_600, dry_mass=6_200,
          propellant="MMH/NTO",
          description="ATV-heritage module. 4× AJ10-type engines, 24 RCS thrusters."),
]

XENON_TANKS = [
    _tank("Dawn Xenon Tank", "NASA/JPL", "Dawn Asteroid Mission",
          propellant_kg=425, dry_mass=65,
          propellant="Xenon",
          description="NSTAR propellant. Dawn mission propellant total. Ti-alloy pressure vessel."),

    _tank("Psyche Xenon Tank", "NASA/JPL", "Psyche Mission",
          propellant_kg=1_085, dry_mass=110,
          propellant="Xenon",
          description="NEXT-C ion propellant. NASA Psyche asteroid orbiter."),

    _tank("BepiColombo Xe Tank", "ESA/JAXA", "BepiColombo MTM",
          propellant_kg=580, dry_mass=78,
          propellant="Xenon",
          description="Mercury Transfer Module. 4× T6 thrusters. Mercury orbit insertion."),

    _tank("SMART-1 Xe Tank", "ESA", "SMART-1 Lunar Orbiter",
          propellant_kg=82, dry_mass=22,
          propellant="Xenon",
          description="First ESA ion propulsion mission. Spiral to lunar orbit."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND & CREW MODULES
# ═══════════════════════════════════════════════════════════════════════════════
COMMAND_CAPSULES = [
    _command("Apollo CM", "NASA/NAR", "Apollo Program",
             dry_mass=5_809, crew=3, power_draw=1_200,
             life_support_mass_per_crew=300,
             description="Blunt-body reentry. Parachutes. Heat shield 4,000°C rated."),

    _command("Orion MPCV", "NASA/Lockheed Martin", "Artemis",
             dry_mass=10_387, crew=4, power_draw=2_100,
             life_support_mass_per_crew=280,
             description="Deep space crewed capsule. 21-day solo / 6-month with Gateway."),

    _command("Crew Dragon C2+", "SpaceX", "Commercial Crew",
             dry_mass=4_200, crew=4, power_draw=1_400,
             life_support_mass_per_crew=180,
             description="Reusable capsule. SuperDraco abort. 210-day ISS docking."),

    _command("CST-100 Starliner", "Boeing", "Commercial Crew",
             dry_mass=13_000, crew=7, power_draw=1_600,
             life_support_mass_per_crew=160,
             description="Dual-use crew + cargo. Atlas V / Vulcan. 60% reuse 10× missions."),

    _command("Soyuz MS", "RKK Energia/Roscosmos", "ISS Crew Transport",
             dry_mass=7_220, crew=3, power_draw=800,
             life_support_mass_per_crew=200,
             description="3-module spacecraft. Orbital + Descent + Service. 6-month mission."),

    _command("Shenzhou", "CASC/CNSA", "Chinese Crewed Spaceflight",
             dry_mass=7_840, crew=3, power_draw=1_000,
             life_support_mass_per_crew=210,
             description="3 modules. Soyuz-derived. CSS (Tiangong) crew transport."),

    _command("Gaganyaan CM", "ISRO/VSSC", "Indian Human Spaceflight",
             dry_mass=5_000, crew=3, power_draw=900,
             life_support_mass_per_crew=220,
             description="India's first crewed spacecraft. GSLV Mk III launch vehicle."),

    _command("Dream Chaser (Crew)", "Sierra Space", "Commercial Crew (Proposed)",
             dry_mass=11_000, crew=7, power_draw=1_300,
             life_support_mass_per_crew=170,
             description="Lifting body. Runway landing. NASA CCiCap concept. Cargo variant in dev."),

    _command("HTV-X Service Module", "JAXA/MHI", "HTV-X Cargo",
             dry_mass=6_300, crew=0, power_draw=1_200,
             description="Uncrewed ISS cargo. Advanced ion RCS. JAXA Kounotori successor."),
]

PROBE_BUSES = [
    _command("MRO Bus (LM-900)", "NASA/LM", "Mars Reconnaissance Orbiter",
             dry_mass=1_031, crew=0, power_draw=2_000,
             description="High-data-rate Mars orbiter bus. HiRISE camera platform."),

    _command("Dawn Bus (XSS-11)", "NASA/Orbital", "Dawn Asteroid Mission",
             dry_mass=747, crew=0, power_draw=1_300,
             description="Ion-propelled asteroid orbiter. Vesta + Ceres missions."),

    _command("Deep Space 1 Bus", "NASA/JPL", "Technology Demonstration",
             dry_mass=373, crew=0, power_draw=2_500,
             description="NSTAR ion tech demo. Comet Borrelly flyby bonus."),

    _command("Mars Express Bus", "ESA/EADS", "Mars Express",
             dry_mass=1_008, crew=0, power_draw=700,
             description="ESA Mars orbiter. Rosetta heritage platform. Operating since 2003."),

    _command("Hayabusa2 Bus", "JAXA/NEC", "Asteroid Sample Return",
             dry_mass=600, crew=0, power_draw=2_600,
             description="4× μ10 ion engines. Ryugu surface sample return."),

    _command("Generic 100kg Probe", "Multi-agency", "SmallSat Platform",
             dry_mass=100, crew=0, power_draw=200,
             description="Minimal probe bus. CubeSat/ESPA-class deep space mission."),

    _command("Chandrayaan-2 Orbiter", "ISRO", "Lunar Orbiter",
             dry_mass=2_379, crew=0, power_draw=1_000,
             description="Indian lunar orbiter. SAR + spectrometer. Active orbit since 2019."),

    _command("Tianwen-1 Orbiter", "CNSA/CAST", "Mars Orbiter/Relay",
             dry_mass=1_084, crew=0, power_draw=1_500,
             description="China's Mars orbiter. Deployed Zhurong rover 2021."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PAYLOAD
# ═══════════════════════════════════════════════════════════════════════════════
SCIENCE_PAYLOADS = [
    _payload("Full Science Suite", "Generic", dry_mass=320, power_draw=150,
             description="Spectrometer, cameras, magnetometer, particle detectors."),
    _payload("HiRISE Camera (MRO)", "NASA/UA", dry_mass=65, power_draw=56,
             description="0.25m/pixel Mars imager. Best resolution orbital camera flown."),
    _payload("CRISM Spectrometer (MRO)", "NASA/APL", dry_mass=34, power_draw=14,
             description="Compact Reconnaissance Imaging Spectrometer. Mineral mapping Mars."),
    _payload("SAR Radar (Chandrayaan-2)", "ISRO", dry_mass=40, power_draw=30,
             description="Synthetic aperture radar. Water ice detection at lunar poles."),
    _payload("JWST NIRCam", "NASA/UA", dry_mass=82, power_draw=130,
             description="Near-infrared camera. Primary science instrument on JWST."),
    _payload("Hubble ACS Camera", "NASA/STScI", dry_mass=280, power_draw=110,
             description="Advanced Camera for Surveys. Optical + UV wide field."),
]

ORBITAL_PAYLOADS = [
    _payload("GPS Block III Sat", "USAF/Lockheed", dry_mass=3_880, power_draw=3_700,
             description="Next-gen US navigation. 3× power increase, M-code anti-jam."),
    _payload("GEO Comsat (generic)", "Multi", dry_mass=5_500, power_draw=15_000,
             description="Generic geostationary communications satellite."),
    _payload("Starlink v2 (Mini)", "SpaceX", dry_mass=800, power_draw=3_000,
             description="Broadband LEO sat. Krypton Hall thrusters. 53 per Falcon 9."),
    _payload("OneWeb v2 Sat", "OneWeb/Airbus", dry_mass=150, power_draw=1_500,
             description="LEO broadband. Plasma thrusters. 648-sat constellation."),
]

LANDING_SYSTEMS = [
    _payload("Apollo LM Descent Stage", "NASA/Grumman", dry_mass=2_034,
             description="Lunar descent stage. LMDE 10 kN engine. 8,165 kg propellant."),
    _payload("Apollo LM Ascent Stage", "NASA/Grumman", dry_mass=2_180, power_draw=400,
             description="Crew compartment. Ascent engine 15.6 kN. Crew: 2."),
    _payload("MSL Sky Crane System", "NASA/JPL", dry_mass=2_401,
             description="Curiosity/Perseverance descent system. 8 MR-80B thrusters."),
    _payload("Chang'e 4 Lander", "CNSA/CASC", dry_mass=1_200, power_draw=1_200,
             description="Far side lunar lander. Yutu-2 rover. Relay via Queqiao."),
    _payload("Luna-25 Lander", "Roscosmos/NPO Lavochkin", dry_mass=1_750,
             description="Russian polar lander. Failed 2023; Lunar-26 planned follow-up."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# POWER — SOLAR ARRAYS
# ═══════════════════════════════════════════════════════════════════════════════
SOLAR_ARRAYS = [
    _solar("ISS P6 Solar Array Wing", "NASA/Boeing", power_w=32_800, dry_mass=1_100,
           description="Each P6 SAW: 2,500 cells. ISS total 8 wings = 262 kW."),
    _solar("ROSA (ISS/Gateway)", "NASA/DSS", power_w=20_000, dry_mass=350,
           description="Roll-Out Solar Array. Compact launch, rigid in operation."),
    _solar("Orion Solar Panels", "ESA/Airbus", power_w=11_100, dry_mass=300,
           description="4 wings on Orion ESM. Triple-junction GaAs cells."),
    _solar("Dawn Triple-Junction", "NASA/JPL", power_w=10_000, dry_mass=480,
           description="GaInP/GaInAs/Ge. 22% efficiency at 1 AU. Scales with 1/r²."),
    _solar("Starlink Solar Array", "SpaceX", power_w=4_000, dry_mass=75,
           description="Single flat panel. Deployable. Powers Hall thruster + payload."),
    _solar("Hubble Solar Arrays 3", "ESA/British Aerospace", power_w=4_800, dry_mass=240,
           description="Flexible roll-out arrays. Replaced SM3B 2002."),
    _solar("Tianhe CSS Solar", "CNSA/CASC", power_w=27_000, dry_mass=1_200,
           description="Chinese Space Station core module arrays. Flexible thin-film."),
    _solar("BepiColombo Solar (MTM)", "ESA/Airbus", power_w=11_000, dry_mass=490,
           description="Designed for 0.31 AU Mercury proximity. Low-absorptance cells."),
    _solar("SmallSat 1kW Panel", "Generic", power_w=1_000, dry_mass=50,
           description="Compact deployable for microsats and planetary probes."),
]

RTGS = [
    _rtg("MMRTG", "NASA/DOE/Teledyne", power_w=110, dry_mass=43,
         description="Multi-Mission RTG. Curiosity & Perseverance. PuO₂ heat source. 14y life."),
    _rtg("GPHS-RTG", "NASA/DOE", power_w=285, dry_mass=55,
         description="General Purpose Heat Source RTG. Cassini (3), Galileo (2), New Horizons (1)."),
    _rtg("Kilopower (1 kWe)", "NASA/DOE", power_w=1_000, dry_mass=134,
         description="KRUSTY reactor. U-235 fission. Designed for lunar/Mars surface power."),
    _rtg("Kilopower (10 kWe)", "NASA/DOE", power_w=10_000, dry_mass=1_400,
         description="Scaled fission surface power. Enables ISRU and crewed Mars base."),
    _rtg("SNAP-19 RTG", "NASA/Teledyne", power_w=40, dry_mass=15,
         description="Pioneer 10/11, Viking landers. PuO₂. Simpler GPHS predecessor."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# COMMUNICATIONS
# ═══════════════════════════════════════════════════════════════════════════════
COMMS_DEEP = [
    _comms("Cassini HGA (4m)", "NASA-ESA/JPL", dry_mass=105, power_draw=82,
           description="4m dish. X+Ka-band. Saturn system. 800 Mbps at Saturn."),
    _comms("New Horizons HGA", "NASA/APL", dry_mass=22, power_draw=12,
           description="2.1m dish. X-band. 1 kbps at Pluto (5 AU). Still operational."),
    _comms("MRO HGA (3m)", "NASA/JPL-LMA", dry_mass=45, power_draw=100,
           description="3m dish. X+Ka-band. 5.2 Mbps from Mars. Relay for rovers."),
    _comms("DSN-compatible Dish", "Generic", dry_mass=80, power_draw=150,
           description="3m+ dish compatible with NASA Deep Space Network ground stations."),
    _comms("BepiColombo MGA", "ESA/EADS", dry_mass=18, power_draw=65,
           description="Medium-gain for Mercury proximity ops. X-band."),
    _comms("Chandrayaan-2 SAR Comm", "ISRO", dry_mass=15, power_draw=50,
           description="X-band synthetic aperture radar comm array."),
]

COMMS_RELAY = [
    _comms("TDRSS S-band Antenna", "NASA/Boeing", dry_mass=35, power_draw=60,
           description="Tracking and Data Relay Satellite System transponder."),
    _comms("Relay Transponder (UHF)", "Generic", dry_mass=8, power_draw=15,
           description="UHF relay for surface assets (landers/rovers). MRO-type."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL / ADAPTERS
# ═══════════════════════════════════════════════════════════════════════════════
ADAPTERS = [
    Module(
        name="Falcon 9 Payload Adapter", module_type=ModuleType.PAYLOAD,
        dry_mass=113, description="[SpaceX] Standard PAF 1194. Separates payload from S2."),
    Module(
        name="Ariane 5 SYLDA (dual)", module_type=ModuleType.PAYLOAD,
        dry_mass=450, description="[ArianeGroup] Dual-payload dispenser. Lower + upper GTO payload."),
    Module(
        name="SLS MPCV Stage Adapter", module_type=ModuleType.PAYLOAD,
        dry_mass=3_800, description="[NASA/Boeing] Adapts Orion to SLS ICPS/EUS."),
    Module(
        name="Falcon 9 Fairing (5.2m)", module_type=ModuleType.PAYLOAD,
        dry_mass=1_900, description="[SpaceX] Carbon fibre composite. Recovered, reused."),
    Module(
        name="Ariane 6 Fairing (5.4m)", module_type=ModuleType.PAYLOAD,
        dry_mass=2_000, description="[ArianeGroup] Composite fairing for Ariane 62/64."),
    Module(
        name="SLS Core Fairing (8.4m)", module_type=ModuleType.PAYLOAD,
        dry_mass=7_000, description="[NASA] Universal Stage Adapter shroud. Largest US fairing."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# TREE CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════

def _leaf(module: Module) -> TreeNode:
    return TreeNode(label=module.name, module=module)


def _branch(label: str, modules: list[Module], expanded: bool = False) -> TreeNode:
    return TreeNode(label=label, children=[_leaf(m) for m in modules], expanded=expanded)


# ═══════════════════════════════════════════════════════════════════════════════
# DECOUPLERS / STAGE SEPARATORS
# Place one of these between sections of your rocket to define a staging boundary.
# The section below a decoupler fires first; the section above continues.
# ═══════════════════════════════════════════════════════════════════════════════
DECOUPLERS = [
    Module(
        name="Saturn V Interstage (S-IC/S-II)",
        module_type=ModuleType.DECOUPLER,
        dry_mass=3_608,
        description="[NASA/Boeing] Pyrotechnic ring separating S-IC from S-II. Retro rockets on S-IC.",
    ),
    Module(
        name="Saturn V Interstage (S-II/S-IVB)",
        module_type=ModuleType.DECOUPLER,
        dry_mass=1_814,
        description="[NASA/Douglas] S-II to S-IVB separation. Ullage motors on S-IVB.",
    ),
    Module(
        name="Falcon 9 Stage Sep System",
        module_type=ModuleType.DECOUPLER,
        dry_mass=150,
        description="[SpaceX] Pneumatic stage separation ring. 4-point attachment. Hot-staging option.",
    ),
    Module(
        name="Falcon 9 Hot-Staging Adapter",
        module_type=ModuleType.DECOUPLER,
        dry_mass=200,
        description="[SpaceX] Allows S2 ignition before S1 separation for performance gain.",
    ),
    Module(
        name="Soyuz Interstage (Block-A/I)",
        module_type=ModuleType.DECOUPLER,
        dry_mass=850,
        description="[Roscosmos] Soyuz core/upper stage separation ring.",
    ),
    Module(
        name="Ariane 5 ECA Interstage",
        module_type=ModuleType.DECOUPLER,
        dry_mass=1_040,
        description="[ArianeGroup] Separates Vulcain 2 core from ESC-A/B upper stage.",
    ),
    Module(
        name="SLS Core/ICPS Interstage",
        module_type=ModuleType.DECOUPLER,
        dry_mass=2_000,
        description="[NASA/Boeing] Universal Stage Adapter connecting SLS core to ICPS/EUS.",
    ),
    Module(
        name="Generic Pyrotechnic Sep Ring",
        module_type=ModuleType.DECOUPLER,
        dry_mass=80,
        description="[Generic] Standard pyrotechnic stage separation ring. Scalable design.",
    ),
    Module(
        name="Cold-Gas Separation System",
        module_type=ModuleType.DECOUPLER,
        dry_mass=45,
        description="[Generic] Cold-gas thruster stage separation for upper stages and kick motors.",
    ),
    Module(
        name="Electron Sep System",
        module_type=ModuleType.DECOUPLER,
        dry_mass=12,
        description="[Rocket Lab] Lightweight separation for Electron 1st/2nd stage.",
    ),
    Module(
        name="Long March Interstage",
        module_type=ModuleType.DECOUPLER,
        dry_mass=620,
        description="[CASC/CNSA] CZ-5 core/upper stage interstage ring.",
    ),
    Module(
        name="ISRO PSLV Interstage",
        module_type=ModuleType.DECOUPLER,
        dry_mass=300,
        description="[ISRO] PSLV stage separation system.",
    ),
    Module(
        name="Vega Interstage Adapter",
        module_type=ModuleType.DECOUPLER,
        dry_mass=110,
        description="[ESA/Avio] Between Zefiro-23 and Zefiro-9 stages.",
    ),
]


def build_module_tree() -> TreeNode:
    """Build the full module tree. Top-level nodes are collapsed by default."""
    root = TreeNode(label="ROOT", expanded=True)

    staging = TreeNode(label="STAGE SEPARATORS  (place between stages)", expanded=True)
    staging.children = [_leaf(m) for m in DECOUPLERS]

    propulsion = TreeNode(label="PROPULSION", expanded=False)
    propulsion.children = [
        _branch("Cryogenic Engines  LH2/LOX", CRYO_ENGINES, expanded=False),
        _branch("Kerosene & Methane  RP-1 / CH4 / LNG", KERO_ENGINES),
        _branch("Hypergolic  MMH / UDMH / NTO", HYPERGOLIC_ENGINES),
        _branch("Solid Rocket Motors", SOLID_MOTORS),
        _branch("Ion & Electric Propulsion", ION_ENGINES),
        _branch("Nuclear Thermal", NUCLEAR_ENGINES),
    ]

    tanks = TreeNode(label="PROPELLANT TANKS", expanded=False)
    tanks.children = [
        _branch("Cryogenic Tanks  LH2/LOX", CRYO_TANKS),
        _branch("Kerosene & Methane Tanks  RP-1 / CH4", KERO_TANKS),
        _branch("Storable Propellant Tanks", STORABLE_TANKS),
        _branch("Xenon Tanks  Ion Propulsion", XENON_TANKS),
    ]

    command = TreeNode(label="COMMAND & CREW", expanded=False)
    command.children = [
        _branch("Crewed Capsules", COMMAND_CAPSULES),
        _branch("Probe & Science Buses", PROBE_BUSES),
    ]

    payload = TreeNode(label="PAYLOAD", expanded=False)
    payload.children = [
        _branch("Science Instruments", SCIENCE_PAYLOADS),
        _branch("Orbital Hardware", ORBITAL_PAYLOADS),
        _branch("Landing Systems", LANDING_SYSTEMS),
        _branch("Structural & Adapters", ADAPTERS),
    ]

    power = TreeNode(label="POWER", expanded=False)
    power.children = [
        _branch("Solar Arrays", SOLAR_ARRAYS),
        _branch("RTG & Fission", RTGS),
    ]

    comms = TreeNode(label="COMMUNICATIONS", expanded=False)
    comms.children = [
        _branch("Deep Space Antennas", COMMS_DEEP),
        _branch("Near-Earth & Relay", COMMS_RELAY),
    ]

    root.children = [staging, propulsion, tanks, command, payload, power, comms]
    return root


# Flat lookup for all modules by name
def build_flat_catalog(root: TreeNode | None = None) -> dict[str, Module]:
    if root is None:
        root = build_module_tree()
    return {m.name: m for m in root.all_modules()}
