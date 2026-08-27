#!/usr/bin/env python3
"""Canonical hashes used to bind Pretty evidence to one run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


COMMON_BUNDLE_FILES = (
    "references/quality-principles.md",
    "references/quality-routing.md",
    "references/quality-review-protocol.md",
    "references/runtime-authorization.md",
    "scripts/disabled_test_scope.py",
    "scripts/quality_registry.py",
    "scripts/evidence_binding.py",
    "scripts/quality_contract_gate.py",
    "scripts/quality_resolver.py",
    "scripts/pretty_tmp.py",
    "scripts/validate_pretty_consistency.py",
    "../pretty-executing/assets/execution.md",
)


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def bytes_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: Path) -> str:
    return bytes_sha256(path.read_bytes())


def payload_sha256(payload: Mapping[str, object], excluded: Iterable[str] = ()) -> str:
    excluded_keys = frozenset(excluded)
    bound_payload = {key: value for key, value in payload.items() if key not in excluded_keys}
    return bytes_sha256(canonical_json_bytes(bound_payload))


def candidate_sha256(parts: Mapping[str, str | bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(parts.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8") if isinstance(content, str) else content)
        digest.update(b"\0")
    return digest.hexdigest()


def bundle_sha256(root: Path, extra_files: Iterable[Path] = ()) -> str:
    """Hash the canonical shared rule bundle and any phase-specific contracts."""
    paths = [root / relative for relative in COMMON_BUNDLE_FILES]
    paths.extend(path for path in extra_files if path.is_file())
    digest_parts: dict[str, str | bytes] = {}
    for path in sorted({path.resolve() for path in paths if path.is_file()}):
        try:
            label = str(path.relative_to(root))
        except ValueError:
            label = str(path)
        digest_parts[label] = path.read_bytes()
    return candidate_sha256(digest_parts)


def evidence_sha256(payload: Mapping[str, object]) -> str:
    """Bind every evidence field, including its source-candidate binding."""
    return payload_sha256(payload, {"evidence_sha256"})


def self_bound_sha256(payload: Mapping[str, object], field: str = "candidate_sha256") -> str:
    """Hash evidence content before its self digest and integrity digest are added."""
    return payload_sha256(payload, {field, "evidence_sha256"})
