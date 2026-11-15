"""A library of checked agent enemies per setting, kept in a JSON file.

Every enemy of a valid act pack (agent/act_pack.py) is stored with its
setting and tier, so later runs in the same setting can draw a whole pack
from earlier ones instead of asking the model again (act_pack decides when).

The file is the path in CONTENT_LIBRARY_PATH; without the variable the
library is off - nothing is read or written. Layout:

    {"settings": {"cyberpunk": {"early": [<Enemy>, ...], "mid": [...], "elite": [...]}}}

Settings are keyed lowercased and trimmed, so " Cyberpunk" and "cyberpunk"
share one shelf. A shelf (setting x tier) holds at most MAX_PER_TIER
enemies, newest last; the oldest fall out first.

Writes are a read-modify-write under one process-wide lock (the API runs
packs on worker threads) and land atomically: a temp file in the same
directory, then os.replace, so a reader never sees half a file. A file that
can't be read or parsed counts as an empty library - it is content, never
worth a crash - and the next write replaces it.
"""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
import threading
from pathlib import Path

from pydantic import ValidationError

from ..models import Enemy

logger = logging.getLogger(__name__)

PATH_ENV = "CONTENT_LIBRARY_PATH"
MAX_PER_TIER = 60

_lock = threading.Lock()

Shelves = dict[str, dict[str, list[Enemy]]]


def library_path() -> Path | None:
    """The library file, None while the library is off."""
    value = os.environ.get(PATH_ENV, "").strip()
    return Path(value) if value else None


def setting_key(setting: str) -> str:
    return setting.strip().lower()


def entries(setting: str) -> dict[str, list[Enemy]]:
    """The setting's enemies per tier, oldest first - empty if the library is
    off, has nothing for it, or its file is broken."""
    path = library_path()
    if path is None:
        return {}
    with _lock:
        return _load(path).get(setting_key(setting), {})


def store(setting: str, tiers: dict[str, list[Enemy]]) -> None:
    """Add the enemies to the setting's shelves, trimming each to
    MAX_PER_TIER. A write that fails is logged, never raised: losing a
    library entry must not cost the player their pack."""
    path = library_path()
    if path is None or not any(tiers.values()):
        return
    key = setting_key(setting)
    with _lock:
        shelves = _load(path)
        setting_shelves = shelves.setdefault(key, {})
        for tier, enemies in tiers.items():
            shelf = setting_shelves.setdefault(tier, []) + list(enemies)
            setting_shelves[tier] = shelf[-MAX_PER_TIER:]
        try:
            _write(path, shelves)
        except OSError:
            logger.warning("content library: could not write %s", path, exc_info=True)


def draw(
    setting: str, counts: dict[str, int], minimum: int, rng: random.Random
) -> dict[str, list[Enemy]] | None:
    """`counts[tier]` distinct enemies per tier, picked at random - None if
    any tier has fewer than `minimum` (or than it asks for)."""
    shelves = entries(setting)
    if any(len(shelves.get(tier, [])) < max(minimum, count) for tier, count in counts.items()):
        return None
    return {
        tier: [enemy.model_copy(deep=True) for enemy in rng.sample(shelves[tier], count)]
        for tier, count in counts.items()
    }


def _load(path: Path) -> Shelves:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("content library: %s is unreadable, treating it as empty", path)
        return {}
    try:
        return {
            str(setting): {
                str(tier): [Enemy.model_validate(enemy) for enemy in enemies]
                for tier, enemies in tiers.items()
            }
            for setting, tiers in raw["settings"].items()
        }
    except (KeyError, TypeError, AttributeError, ValidationError):
        logger.warning("content library: %s has an unexpected shape, treating it as empty", path)
        return {}


def _write(path: Path, shelves: Shelves) -> None:
    data = {
        "settings": {
            setting: {
                tier: [enemy.model_dump(mode="json") for enemy in enemies]
                for tier, enemies in tiers.items()
            }
            for setting, tiers in shelves.items()
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp:
            json.dump(data, temp, ensure_ascii=False)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
