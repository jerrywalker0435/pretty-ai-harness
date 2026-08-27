#!/usr/bin/env python3
"""Canonical hashes used to bind Pretty evidence to one run."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping


def evidence_sha256(payload: Mapping[str, object]) -> str:
    candidate = {
        key: value
        for key, value in payload.items()
        if key not in {"candidate_sha256", "evidence_sha256"}
    }
    canonical = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
