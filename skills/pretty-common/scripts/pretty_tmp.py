#!/usr/bin/env python3
"""Constrain Pretty runtime artifacts to one topic-local temporary run."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterable


RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
TOPIC = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_topic_dir(topic_dir: Path) -> Path:
    resolved = topic_dir.resolve()
    if resolved.parent.name != "pretty" or resolved.parent.parent.name != "docs":
        raise ValueError(f"Pretty topic must be docs/pretty/<topic>: {topic_dir}")
    if not TOPIC.fullmatch(resolved.name):
        raise ValueError(f"Pretty topic must use lowercase kebab-case: {resolved.name}")
    return resolved


def topic_dir_for_document(document: Path) -> Path:
    return validate_topic_dir(document.resolve().parent)


def run_dir_for(topic_dir: Path, run_id: str) -> Path:
    topic = validate_topic_dir(topic_dir)
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"Pretty run id is invalid: {run_id}")
    return topic / "tmp" / run_id


def validate_run_dir(topic_dir: Path, run_dir: Path) -> Path:
    topic = validate_topic_dir(topic_dir)
    _reject_path_traversal(run_dir)
    resolved = run_dir.resolve()
    if resolved.parent != topic / "tmp" or not RUN_ID.fullmatch(resolved.name):
        expected = topic / "tmp" / "<run-id>"
        raise ValueError(f"Pretty temporary run must be under {expected}: {run_dir}")
    return resolved


def topic_dir_for_run(run_dir: Path) -> Path:
    resolved = run_dir.resolve()
    topic = validate_topic_dir(resolved.parent.parent)
    validate_run_dir(topic, resolved)
    return topic


def validate_artifact_path(run_dir: Path, artifact: Path) -> Path:
    topic = topic_dir_for_run(run_dir)
    resolved_run = validate_run_dir(topic, run_dir)
    _reject_path_traversal(artifact)
    resolved_artifact = artifact.resolve()
    if resolved_artifact.parent != resolved_run or resolved_artifact.name in {"", ".", ".."}:
        raise ValueError(f"Pretty artifact must be directly under {resolved_run}: {artifact}")
    return resolved_artifact


def is_pretty_tmp_path(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return any(
        parts[index:index + 2] == ("docs", "pretty") and parts[index + 3] == "tmp"
        for index in range(max(0, len(parts) - 3))
    )


def registered_artifact_names(names: Iterable[object]) -> set[str]:
    artifacts = set()
    for value in names:
        if not isinstance(value, str) or Path(value).name != value or value in {"", ".", ".."}:
            raise ValueError(f"Invalid Pretty temporary artifact name: {value}")
        artifacts.add(value)
    return artifacts


def assert_cleanup_scope(run_dir: Path, manifest_name: str, artifacts: Iterable[object]) -> set[str]:
    allowed = registered_artifact_names([manifest_name, *artifacts])
    unexpected = sorted(path.name for path in run_dir.iterdir() if path.name not in allowed)
    if unexpected:
        raise ValueError(f"Pretty temporary run contains unregistered files: {', '.join(unexpected)}")
    return allowed


def cleanup_registered_run(
    topic_dir: Path,
    run_dir: Path,
    manifest_name: str,
    artifacts: Iterable[object],
) -> tuple[str, ...]:
    resolved_run = validate_run_dir(topic_dir, run_dir)
    allowed = assert_cleanup_scope(resolved_run, manifest_name, artifacts)
    removed = _unlink_registered(resolved_run, allowed, manifest_name)
    resolved_run.rmdir()
    _remove_empty_tmp_root(resolved_run.parent)
    return tuple(removed)


def _unlink_registered(run_dir: Path, names: set[str], manifest_name: str) -> list[str]:
    removed = []
    for name in sorted(names - {manifest_name}) + [manifest_name]:
        path = validate_artifact_path(run_dir, run_dir / name)
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"Pretty cleanup refuses a directory artifact: {path}")
        path.unlink()
        removed.append(name)
    return removed


def _remove_empty_tmp_root(tmp_root: Path) -> None:
    try:
        tmp_root.rmdir()
    except OSError:
        pass


def _reject_path_traversal(path: Path) -> None:
    if ".." in path.parts:
        raise ValueError(f"Pretty path traversal is not allowed: {path}")
