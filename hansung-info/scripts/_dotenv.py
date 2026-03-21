#!/usr/bin/env python3
"""Tiny .env loader (best-effort).

We keep this dependency-free (no python-dotenv) so the skill works out of the box.
Only sets env vars that are currently missing.
"""

from __future__ import annotations

import os
import pathlib


def load_dotenv(path: str | pathlib.Path | None = None) -> None:
    if path is None:
        path = pathlib.Path.home() / ".openclaw" / ".env"
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        return

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if os.getenv(k) is None:
            os.environ[k] = v
