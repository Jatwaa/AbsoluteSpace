"""
Historical mission programs — replications of real interplanetary missions.

These appear on the Operations board alongside Congressional tasking. Each maps
a real probe/orbiter/lander to one of the simulated planets, with a payload
requirement, a difficulty-scaled reward, and a short historical note. (All are
uncrewed planetary missions — the real crewed programs were lunar/LEO, which
this solar-system model doesn't yet include.)
"""

from __future__ import annotations
from .contracts import MissionContract, ContractStatus
from sim.transfer import mission_delta_v_budget

# (key, title, year, destination, objective, payload keywords, reward, blurb)
_HISTORICAL = [
    ("MARINER2", "Mariner 2", 1962, "Venus", "Flyby Probe",
     ["Science", "Probe", "Spectrometer", "Suite"], 150,
     "First successful interplanetary flyby — confirmed Venus' searing surface."),
    ("MARINER4", "Mariner 4", 1964, "Mars", "Flyby Probe",
     ["Science", "Camera", "Probe", "Suite"], 160,
     "Returned the first close-up images of another planet (Mars)."),
    ("VIKING1", "Viking 1", 1975, "Mars", "Lander",
     ["Lander", "Descent", "Sky Crane", "Science"], 300,
     "First fully successful Mars landing and long-duration surface ops."),
    ("VOYAGER2", "Voyager 2", 1977, "Saturn", "Flyby Probe",
     ["Science", "Probe", "Camera", "Suite"], 360,
     "Grand Tour of the outer planets — still operating in interstellar space."),
    ("MAGELLAN", "Magellan", 1989, "Venus", "Science Orbiter",
     ["SAR", "Radar", "Science", "Spectrometer"], 240,
     "Radar-mapped 98% of Venus' surface through its clouds."),
    ("GALILEO", "Galileo", 1989, "Jupiter", "Science Orbiter",
     ["Science", "Spectrometer", "Camera", "Suite"], 380,
     "First Jupiter orbiter; dropped an atmospheric entry probe."),
    ("CASSINI", "Cassini", 1997, "Saturn", "Science Orbiter",
     ["Science", "Spectrometer", "Camera", "Suite"], 420,
     "Studied Saturn and its moons for 13 years; delivered the Huygens lander."),
    ("MESSENGER", "MESSENGER", 2004, "Mercury", "Science Orbiter",
     ["Science", "Spectrometer", "Camera", "Suite"], 340,
     "First spacecraft to orbit Mercury after a series of gravity assists."),
    ("MSL", "Mars Science Laboratory (Curiosity)", 2011, "Mars", "Lander",
     ["Sky Crane", "Lander", "Descent", "Science"], 360,
     "Sky-crane landing of a car-sized nuclear rover in Gale Crater."),
    ("JUNO", "Juno", 2011, "Jupiter", "Science Orbiter",
     ["Science", "Spectrometer", "Camera", "Suite"], 380,
     "Polar Jupiter orbiter probing the planet's deep structure and aurorae."),
]


def generate_historical(bodies, sim_time, start_id, count=4):
    """Build a rotating selection of historical-mission contracts."""
    out = []
    sun, earth = bodies["Sun"], bodies["Earth"]
    for i in range(count):
        key, title, year, dest, obj, payload, reward, blurb = _HISTORICAL[
            (start_id + i) % len(_HISTORICAL)]
        body = bodies[dest]
        budget = mission_delta_v_budget(earth, body, sun)
        out.append(MissionContract(
            id=f"H{start_id + i:03d}",
            title=f"{title} ({year})",
            objective=obj,
            description=f"Historical replication — {blurb}",
            origin="Earth",
            destination=dest,
            required_delta_v=budget["total_one_way"],
            required_crew=0,
            payload_keywords=payload,
            reward=reward,
            source="HISTORICAL",
        ))
    return out
