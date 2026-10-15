"""Puts the platform services (Switchboard, Atlas, Checkpoint) on sys.path so tests run the real code in process.
They live in sibling directories of this monorepo and are not installable packages."""

import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[2]
for service in ("switchboard", "atlas", "checkpoint"):
    path = str(PLATFORM / service)
    if path not in sys.path:
        sys.path.append(path)
