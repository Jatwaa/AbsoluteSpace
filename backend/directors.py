"""
Director identities.

Every connection is assigned a Director number. A player can rename it and
secure it with a PIN. A secured Director can be resumed later (same or another
machine) by supplying its number + PIN — which also restores ownership of that
Director's contracts and fleet.

PINs are stored only as salted SHA-256 hashes; the plaintext is never persisted,
so a lost PIN cannot be recovered. Profiles persist to a local JSON file so they
survive server restarts.

NOTE: this is lightweight identity for a casual multiplayer game, not strong
authentication. Do not reuse a sensitive PIN here.
"""

from __future__ import annotations
import os
import json
import random
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Optional

DIRECTORS_PATH = os.path.join(os.path.dirname(__file__), "directors.json")


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


@dataclass
class Director:
    number: int
    name: str
    pin_hash: Optional[str] = None
    salt: Optional[str] = None

    @property
    def secured(self) -> bool:
        return self.pin_hash is not None

    @property
    def id(self) -> str:
        return str(self.number)

    def public(self) -> dict:
        return {"directorId": self.id, "name": self.name, "secured": self.secured}

    def to_json(self) -> dict:
        return {"number": self.number, "name": self.name,
                "pin_hash": self.pin_hash, "salt": self.salt}


class DirectorRegistry:
    def __init__(self, path: str = DIRECTORS_PATH):
        self.path = path
        self.directors: dict[int, Director] = {}
        self._load()

    # ── persistence ──
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("directors", []):
                self.directors[d["number"]] = Director(
                    number=d["number"], name=d["name"],
                    pin_hash=d.get("pin_hash"), salt=d.get("salt"))
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self.directors = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"directors": [d.to_json() for d in self.directors.values()]},
                          f, indent=2)
        except OSError:
            pass

    # ── operations ──
    def assign_new(self) -> Director:
        for _ in range(10000):
            n = random.randint(1000, 9999)
            if n not in self.directors:
                break
        else:
            n = max(self.directors) + 1
        d = Director(number=n, name=f"Director-{n}")
        self.directors[n] = d
        self._save()
        return d

    def get(self, number) -> Optional[Director]:
        try:
            return self.directors.get(int(number))
        except (TypeError, ValueError):
            return None

    def rename(self, number, name: str) -> Optional[Director]:
        d = self.get(number)
        if d:
            d.name = name.strip()[:24] or d.name
            self._save()
        return d

    def set_pin(self, number, pin: str) -> dict:
        d = self.get(number)
        if not d:
            return {"error": "director not found"}
        pin = (pin or "").strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            return {"error": "PIN must be 4-8 digits"}
        d.salt = secrets.token_hex(8)
        d.pin_hash = _hash_pin(pin, d.salt)
        self._save()
        return {"ok": True}

    def verify(self, number, pin: str) -> bool:
        d = self.get(number)
        if not d or not d.secured:
            return False
        return _hash_pin((pin or "").strip(), d.salt) == d.pin_hash

    def clear_pin(self, number, pin: str) -> dict:
        d = self.get(number)
        if not d:
            return {"error": "director not found"}
        if d.secured and not self.verify(number, pin):
            return {"error": "incorrect PIN"}
        d.pin_hash = None
        d.salt = None
        self._save()
        return {"ok": True}
