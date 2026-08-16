"""Fingerprint of web/ so the monitor can reload when files change."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .config import WEB_DIR


def web_asset_version() -> str:
    h = hashlib.sha256()
    if not WEB_DIR.is_dir():
        return "missing"
    files = sorted(p for p in WEB_DIR.iterdir() if p.is_file())
    if not files:
        return "empty"
    for path in files:
        st = path.stat()
        h.update(path.name.encode())
        h.update(str(st.st_mtime_ns).encode())
        h.update(str(st.st_size).encode())
    return h.hexdigest()[:16]
