"""Engine constants read from thrust.6502, so the tools don't copy them by hand.

    OBJECT_TYPES       {name: type byte} for every `OBJECT_<lower_case> = $xx`,
                       e.g. OBJECT_TYPES["door"] == 0x11
    OBJECT_NAMES       {type byte: name}, the inverse
    LEVEL_MAX_OBJECTS  highest object index per level ($1F)
    LEVEL_OBJECT_CAP   objects per level (LEVEL_MAX_OBJECTS + 1)

Only plain `NAME = $hex|&hex|decimal` assignments are parsed. Most object
types sit inside feature-flag IF blocks, but each has a single value, so
reading them without evaluating the flags is safe.
"""

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "thrust.6502"

_ASSIGN_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([$&][0-9A-Fa-f]+|\d+)\b", re.MULTILINE)


def _value(text):
    return int(text[1:], 16) if text[0] in "$&" else int(text)


def parse(path=SOURCE):
    """Return {name: int} for every simple numeric assignment in `path`."""
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    return {m.group(1): _value(m.group(2)) for m in _ASSIGN_RE.finditer(source)}


_CONSTS = parse()

OBJECT_TYPES = {name[len("OBJECT_"):]: v for name, v in _CONSTS.items()
                if re.fullmatch(r"OBJECT_[a-z][a-z0-9_]*", name)}
OBJECT_NAMES = {v: name for name, v in OBJECT_TYPES.items()}
LEVEL_MAX_OBJECTS = _CONSTS["LEVEL_MAX_OBJECTS"]
LEVEL_OBJECT_CAP = LEVEL_MAX_OBJECTS + 1
