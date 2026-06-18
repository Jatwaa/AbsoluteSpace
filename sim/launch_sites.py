"""Real-world orbital launch sites with coordinates, climate zone, and pad data."""

from __future__ import annotations
from dataclasses import dataclass, field
import math


@dataclass
class LaunchSite:
    id: str
    name: str
    short: str          # 8-char display label
    agency: str
    country: str
    latitude: float     # degrees N
    longitude: float    # degrees E
    altitude: float     # m ASL
    climate: str        # "tropical" | "subtropical" | "temperate" | "arid" | "continental"
    pads: list[str]

    # Operational constraints
    max_wind_surface: float = 15.0    # m/s  (~30 kt)
    max_wind_upper: float   = 35.0    # m/s at 60 kft
    min_visibility: float   = 7400.0  # m (4 sm)

    @property
    def lat_str(self) -> str:
        d = abs(self.latitude)
        return f"{d:.3f}°{'N' if self.latitude >= 0 else 'S'}"

    @property
    def lon_str(self) -> str:
        d = abs(self.longitude)
        return f"{d:.3f}°{'E' if self.longitude >= 0 else 'W'}"

    @property
    def coords(self) -> str:
        return f"{self.lat_str}  {self.lon_str}"

    def surface_speed(self) -> float:
        """Earth's rotational surface speed at this latitude (m/s) — launch bonus."""
        R = 6_371_000.0
        omega = 7.2921e-5
        return R * omega * math.cos(math.radians(self.latitude))


LAUNCH_SITES: list[LaunchSite] = [
    LaunchSite(
        id="KSC_39A",
        name="Kennedy Space Center LC-39A",
        short="KSC 39A",
        agency="NASA / SpaceX",
        country="USA",
        latitude=28.6081,
        longitude=-80.6043,
        altitude=3.0,
        climate="subtropical",
        pads=["LC-39A"],
        max_wind_surface=15.4,
    ),
    LaunchSite(
        id="KSC_39B",
        name="Kennedy Space Center LC-39B",
        short="KSC 39B",
        agency="NASA",
        country="USA",
        latitude=28.6272,
        longitude=-80.6208,
        altitude=3.0,
        climate="subtropical",
        pads=["LC-39B"],
        max_wind_surface=15.4,
    ),
    LaunchSite(
        id="CCAFS_SLC40",
        name="Cape Canaveral SLC-40",
        short="CC SLC40",
        agency="SpaceX",
        country="USA",
        latitude=28.5618,
        longitude=-80.5773,
        altitude=3.0,
        climate="subtropical",
        pads=["SLC-40"],
        max_wind_surface=15.4,
    ),
    LaunchSite(
        id="VAFB_SLC4E",
        name="Vandenberg SFB SLC-4E",
        short="VAFB 4E",
        agency="SpaceX",
        country="USA",
        latitude=34.6321,
        longitude=-120.6110,
        altitude=67.0,
        climate="temperate",
        pads=["SLC-4E"],
        max_wind_surface=13.9,
    ),
    LaunchSite(
        id="BAIKONUR_LC1",
        name="Baikonur Cosmodrome Site 1",
        short="Baikonur",
        agency="Roscosmos",
        country="Kazakhstan",
        latitude=45.9200,
        longitude=63.3420,
        altitude=90.0,
        climate="arid",
        pads=["Site 1/5 (Gagarin's Start)", "Site 31/6"],
        max_wind_surface=15.0,
    ),
    LaunchSite(
        id="VOSTOCHNY",
        name="Vostochny Cosmodrome",
        short="Vostochny",
        agency="Roscosmos",
        country="Russia",
        latitude=51.8840,
        longitude=128.3340,
        altitude=280.0,
        climate="continental",
        pads=["Site 1S"],
        max_wind_surface=15.0,
    ),
    LaunchSite(
        id="KOUROU_ELA3",
        name="Guiana Space Centre ELA-3",
        short="Kourou",
        agency="ESA / Arianespace",
        country="French Guiana",
        latitude=5.2361,
        longitude=-52.7681,
        altitude=12.0,
        climate="tropical",
        pads=["ELA-3", "ELS (Soyuz)"],
        max_wind_surface=12.0,
    ),
    LaunchSite(
        id="TANEGASHIMA_Y2",
        name="Tanegashima Space Centre",
        short="Tanegashma",
        agency="JAXA / MHI",
        country="Japan",
        latitude=30.4004,
        longitude=130.9750,
        altitude=65.0,
        climate="subtropical",
        pads=["Yoshinobu LP-1", "Yoshinobu LP-2"],
        max_wind_surface=14.0,
    ),
    LaunchSite(
        id="SATISH_DHAWAN",
        name="Satish Dhawan Space Centre",
        short="Sriharikota",
        agency="ISRO",
        country="India",
        latitude=13.7199,
        longitude=80.2304,
        altitude=17.0,
        climate="tropical",
        pads=["FLP", "SLP"],
        max_wind_surface=14.0,
    ),
    LaunchSite(
        id="WENCHANG_101",
        name="Wenchang Space Launch Site",
        short="Wenchang",
        agency="CNSA / CASC",
        country="China",
        latitude=19.6145,
        longitude=110.9512,
        altitude=10.0,
        climate="tropical",
        pads=["LC-101", "LC-201"],
        max_wind_surface=13.0,
    ),
    LaunchSite(
        id="JIUQUAN_SLS",
        name="Jiuquan Satellite Launch Centre",
        short="Jiuquan",
        agency="CNSA / CASC",
        country="China",
        latitude=40.9580,
        longitude=100.2980,
        altitude=1000.0,
        climate="arid",
        pads=["SLS-1", "SLS-2"],
        max_wind_surface=15.0,
    ),
    LaunchSite(
        id="NEW_GLENN_LC36",
        name="Cape Canaveral LC-36",
        short="CC LC-36",
        agency="Blue Origin",
        country="USA",
        latitude=28.5657,
        longitude=-80.5667,
        altitude=3.0,
        climate="subtropical",
        pads=["LC-36"],
        max_wind_surface=15.4,
    ),
]

SITES_BY_ID: dict[str, LaunchSite] = {s.id: s for s in LAUNCH_SITES}
