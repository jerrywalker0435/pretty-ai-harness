#!/usr/bin/env python3
"""Freeze inputs and validate evidence for a Pretty Design run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from pretty_tmp import (  # type: ignore[import-not-found]
    cleanup_registered_run,
    is_pretty_tmp_path,
    run_dir_for,
    topic_dir_for_document,
    validate_artifact_path,
    validate_run_dir,
)
from validate_design import validate_design


SCHEMA_VERSION = 2
MANIFEST_NAME = "design-run.json"
EVIDENCE_NAME = "evidence-summary.json"
SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_FILE_LIMIT = 20_000
SNIPPET_LIMIT = 80
MAX_SNIPPET_LENGTH = 220

ENTRY_MARKERS = re.compile(
    r"@(?:RestController|Controller|RequestMapping|GetMapping|PostMapping|PutMapping|"
    r"DeleteMapping|PatchMapping|KafkaListener|RabbitListener|JmsListener|Scheduled|"
    r"EventListener|GrpcService)|public\s+static\s+void\s+main\s*\(",
    re.IGNORECASE,
)
EXTERNAL_MARKERS = re.compile(
    r"@(?:FeignClient|HttpExchange|GetExchange|PostExchange|KafkaListener|RabbitListener)|"
    r"(?:RestTemplate|WebClient|WebClient\.Builder|KafkaTemplate|JmsTemplate)|"
    r"https?://|\b(?:grpc|amqp|kafka|jdbc):",
    re.IGNORECASE,
)
PORT_MARKERS = re.compile(
    r"(?:^|\s)(?:server\.port|management\.server\.port|local\.server\.port|port)\s*[:=]"
    r"\s*[^\s#]+",
    re.IGNORECASE,
)
SCHEMA_MARKERS = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX|SEQUENCE)|\b(?:flyway|liquibase|migration)\b|"
    r"(?:schema|db|database|ddl|sql)/",
    re.IGNORECASE,
)
IGNORED_PARTS = {".git", ".idea", "node_modules", "target", "build", "dist", ".code-review"}
SOURCE_SUFFIXES = {
    ".java", ".kt", ".kts", ".groovy", ".sql", ".xml", ".yaml", ".yml", ".properties", ".json",
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def design_candidate_hash(design: str, prd: str) -> str:
    digest = hashlib.sha256()
    for name, content in (("design.md", design), ("prd.md", prd)):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def repo_root_for(path: Path) -> Path:
    path = path.resolve()
    try:
        process_result = subprocess.run(
            ["git", "-C", str(path if path.is_dir() else path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        fallback = path if path.is_dir() else path.parent
        current = fallback
        while current.parent != current:
            if current.name == "pretty" and current.parent.name == "docs":
                return current.parent.parent.resolve()
            current = current.parent
        return fallback
    return Path(process_result.stdout.strip()).resolve()


def discover_named_files(root: Path, name: str) -> list[Path]:
    files: list[Path] = []
    current = root.resolve()
    while True:
        candidate = current / name
        if candidate.is_file():
            files.append(candidate)
        if current.parent == current:
            break
        current = current.parent
    for candidate in root.rglob(name):
        ignored = any(part in IGNORED_PARTS for part in candidate.parts)
        if candidate.is_file() and not ignored and not is_pretty_tmp_path(relative(candidate, root)):
            if candidate.resolve() not in files:
                files.append(candidate.resolve())
    return sorted(files)


def skill_files() -> list[Path]:
    # Hash the instructions and directly consumed Design contracts.
    paths = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "assets/design.md",
        SKILL_ROOT / "scripts/design_run.py",
        SKILL_ROOT / "scripts/validate_design.py",
        SKILL_ROOT.parent / "pretty-common/references/quality-principles.md",
        SKILL_ROOT.parent / "pretty-common/references/quality-routing.md",
        SKILL_ROOT.parent / "pretty-common/references/runtime-authorization.md",
        SKILL_ROOT.parent / "pretty-common/scripts/pretty_tmp.py",
    ]
    return [path for path in paths if path.is_file()]


def file_records(paths: Iterable[Path], root: Path) -> list[dict[str, str]]:
    return [
        {"path": relative(path, root), "sha256": sha256_file(path)}
        for path in sorted({path.resolve() for path in paths})
    ]


def _manifest_hash(manifest: Mapping[str, object]) -> str:
    without_runtime_hash = {
        key: payload for key, payload in manifest.items() if key not in {"created_at", "manifest_sha256"}
    }
    return sha256_bytes(canonical_json(without_runtime_hash))


def _design_record(design_path: Path | None, root: Path) -> dict[str, str | None]:
    exists = design_path is not None and design_path.is_file()
    return {
        "path": relative(design_path, root) if design_path else None,
        "sha256": sha256_file(design_path) if exists else None,
    }


def _new_manifest(
    prd_path: Path,
    design_path: Path | None,
    root: Path,
    run_id: str,
    run_dir: Path,
) -> dict[str, object]:
    instruction_files = file_records(discover_named_files(root, "AGENTS.md"), root)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "topic": topic_dir_for_document(prd_path).name,
        "run_dir": relative(run_dir, root),
        "status": "frozen",
        "created_at": now(),
        "repo_root": str(root),
        "prd": {"path": relative(prd_path, root), "sha256": sha256_file(prd_path)},
        "design": _design_record(design_path, root),
        "design_frozen": False,
        "instruction_files": instruction_files,
        "skill_files": file_records(skill_files(), root),
        "artifacts": [],
    }
    manifest["manifest_sha256"] = _manifest_hash(manifest)
    return manifest


def freeze_inputs(
    prd_path: Path,
    design_path: Path | None,
    run_dir: Path | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    prd_path = prd_path.resolve()
    root = repo_root_for(prd_path)
    topic_dir = topic_dir_for_document(prd_path)
    if not prd_path.is_file():
        raise FileNotFoundError(f"PRD 不存在：{prd_path}")
    if design_path is not None:
        design_path = design_path.resolve()
        if design_path.exists() and not design_path.is_file():
            raise OSError(f"Design 不是文件：{design_path}")
    selected_run_id = run_id or (run_dir.name if run_dir is not None else uuid.uuid4().hex)
    selected_run_dir = (
        run_dir_for(topic_dir, selected_run_id)
        if run_dir is None
        else validate_run_dir(topic_dir, run_dir)
    )
    if selected_run_dir.name != selected_run_id:
        raise ValueError(f"run id must match run directory name: {selected_run_id}")
    manifest_path = selected_run_dir / MANIFEST_NAME
    if manifest_path.is_file():
        existing = load_json(manifest_path)
        integrity_errors = _manifest_integrity_errors(existing)
        if integrity_errors:
            raise ValueError("；".join(integrity_errors))
        return existing
    selected_run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _new_manifest(prd_path, design_path, root, selected_run_id, selected_run_dir)
    write_json(manifest_path, manifest)
    return manifest


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 必须是 object：{path}")
    return payload


def _current_records(records: object, root: Path) -> list[str]:
    if not isinstance(records, list):
        return ["记录格式无效"]
    errors: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            errors.append("记录格式无效")
            continue
        path = root / record["path"]
        if not path.is_file():
            errors.append(f"文件不存在：{record['path']}")
        elif record.get("sha256") != sha256_file(path):
            errors.append(f"输入已变化：{record['path']}")
    return errors


def frozen_input_errors(manifest: Mapping[str, object]) -> list[str]:
    root = Path(str(manifest.get("repo_root", ""))).resolve()
    errors = _manifest_integrity_errors(manifest)
    for label in ("prd",):
        record = manifest.get(label)
        if not isinstance(record, dict) or not record.get("path"):
            if label == "prd":
                errors.append("冻结清单缺少 PRD")
            continue
        path = root / str(record["path"])
        if not path.is_file():
            errors.append(f"{label} 不存在：{record['path']}")
        elif record.get("sha256") != sha256_file(path):
            errors.append(f"{label} 已变化：{record['path']}")
    errors.extend(_current_records(manifest.get("instruction_files"), root))
    errors.extend(_current_records(manifest.get("skill_files"), root))
    return sorted(set(errors))


def _manifest_integrity_errors(manifest: Mapping[str, object]) -> list[str]:
    expected = manifest.get("manifest_sha256")
    if not isinstance(expected, str) or expected != _manifest_hash(manifest):
        return ["冻结清单哈希不匹配"]
    return []


def _iter_repo_files(root: Path) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        if count >= REPO_FILE_LIMIT:
            break
        relative_path = relative(path, root)
        ignored = any(part in IGNORED_PARTS for part in path.relative_to(root).parts)
        if not path.is_file() or ignored or is_pretty_tmp_path(relative_path):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        count += 1
        yield path


def _snippets(path: Path, pattern: re.Pattern[str], root: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    matches: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, 1):
        if pattern.search(line):
            matches.append({
                "path": relative(path, root),
                "line": line_number,
                "text": " ".join(line.strip().split())[:MAX_SNIPPET_LENGTH],
            })
            if len(matches) >= SNIPPET_LIMIT:
                break
    return matches


def _looks_like_schema(path: Path) -> bool:
    if SCHEMA_MARKERS.search(path.as_posix()):
        return True
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r"\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX|SEQUENCE)\b", content, re.IGNORECASE))


def _prd_contracts(prd: str) -> list[dict[str, str]]:
    contracts = []
    lines = prd.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^###\s+((?:REQ|AC)-\d{3})[：:]\s*(.+)$", line)
        if match:
            contracts.append({"id": match.group(1), "title": match.group(2).strip()})
    return contracts


def _repository_evidence(root: Path) -> dict[str, list[dict[str, object]]]:
    files = list(_iter_repo_files(root))
    entry_points = [match for path in files for match in _snippets(path, ENTRY_MARKERS, root)]
    external_interfaces = [match for path in files for match in _snippets(path, EXTERNAL_MARKERS, root)]
    ports = [match for path in files for match in _snippets(path, PORT_MARKERS, root)]
    schemas = [
        {"path": relative(path, root), "sha256": sha256_file(path)}
        for path in files
        if _looks_like_schema(path)
    ]
    return {
        "entry_points": entry_points,
        "ports": ports,
        "external_interfaces": external_interfaces,
        "schemas": schemas,
    }


def _evidence_source_paths(repository: Mapping[str, object]) -> list[str]:
    source_paths: set[str] = set()
    for category in ("entry_points", "ports", "external_interfaces", "schemas"):
        records = repository.get(category, [])
        if isinstance(records, list):
            source_paths.update(
                str(record["path"])
                for record in records
                if isinstance(record, dict) and isinstance(record.get("path"), str)
            )
    return sorted(source_paths)


def build_evidence_summary(
    prd_path: Path,
    design_path: Path | None,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    root = Path(str(manifest["repo_root"])).resolve()
    prd = prd_path.read_text(encoding="utf-8")
    design = design_path.read_text(encoding="utf-8") if design_path and design_path.is_file() else ""
    repository = _repository_evidence(root)
    source_paths = _evidence_source_paths(repository)
    source_hashes = {
        path: sha256_file(root / path)
        for path in source_paths
        if (root / path).is_file()
    }
    contracts = _prd_contracts(prd)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "candidate_sha256": design_candidate_hash(design, prd),
        "generated_at": now(),
        "contracts": contracts,
        "traceability": _traceability_summary(contracts, design),
        "repository": {
            **repository,
        },
        "source_hashes": source_hashes,
    }


def evidence_staleness_errors(
    summary: Mapping[str, object],
    manifest: Mapping[str, object],
    prd_path: Path,
    design_path: Path | None,
) -> list[str]:
    root = Path(str(manifest["repo_root"])).resolve()
    prd = prd_path.read_text(encoding="utf-8")
    design = design_path.read_text(encoding="utf-8") if design_path and design_path.is_file() else ""
    errors = _candidate_binding_errors(summary, manifest, design, prd)
    source_hashes = summary.get("source_hashes")
    if not isinstance(source_hashes, dict):
        return errors + ["证据摘要缺少 source_hashes"]
    return errors + _source_hash_errors(source_hashes, root)


def bind_evidence_candidate(
    evidence_path: Path,
    prd_path: Path,
    design_path: Path,
    run_id: str | None = None,
) -> dict[str, object]:
    summary = load_json(evidence_path)
    manifest_path = evidence_path.parent / MANIFEST_NAME
    manifest = load_json(manifest_path)
    _validate_manifest_location(manifest_path, manifest)
    validate_artifact_path(evidence_path.parent, evidence_path)
    if run_id is not None and summary.get("run_id") != run_id:
        raise ValueError("证据摘要不属于当前 Design 运行")
    design = design_path.read_text(encoding="utf-8")
    summary["candidate_sha256"] = design_candidate_hash(design, prd_path.read_text(encoding="utf-8"))
    summary["traceability"] = _traceability_summary(summary.get("contracts"), design)
    summary["candidate_bound_at"] = now()
    write_json(evidence_path, summary)
    return summary


def _traceability_summary(contracts: object, design: str) -> dict[str, list[str]]:
    contract_ids = {
        contract["id"]
        for contract in contracts or []
        if isinstance(contract, dict) and isinstance(contract.get("id"), str)
    }
    mapped = set(re.findall(r"\b(?:REQ|AC)-\d{3}\b", design))
    return {"mapped": sorted(mapped), "unmapped": sorted(contract_ids - mapped)}


def _candidate_binding_errors(
    summary: Mapping[str, object],
    manifest: Mapping[str, object],
    design: str,
    prd: str,
) -> list[str]:
    errors: list[str] = []
    if summary.get("run_id") != manifest.get("run_id"):
        errors.append("证据摘要不属于当前 Design 运行")
    if summary.get("candidate_sha256") != design_candidate_hash(design, prd):
        errors.append("证据摘要与当前 PRD/Design 候选不匹配")
    return errors


def _source_hash_errors(source_hashes: Mapping[object, object], root: Path) -> list[str]:
    errors: list[str] = []
    for source_path, expected_hash in source_hashes.items():
        candidate = root / str(source_path)
        if not candidate.is_file():
            errors.append(f"证据来源已删除：{source_path}")
        elif expected_hash != sha256_file(candidate):
            errors.append(f"证据来源已变化：{source_path}")
    return errors


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(canonical_json(payload) + b"\n")
    temporary.replace(path)


def _claim_artifact(manifest_path: Path, artifact_path: Path) -> None:
    manifest = load_json(manifest_path)
    integrity_errors = _manifest_integrity_errors(manifest)
    if integrity_errors:
        raise ValueError("；".join(integrity_errors))
    root = Path(str(manifest["repo_root"])).resolve()
    prd_record = manifest.get("prd")
    if not isinstance(prd_record, dict) or not isinstance(prd_record.get("path"), str):
        raise ValueError("冻结清单缺少 PRD 路径")
    topic_dir = topic_dir_for_document(root / str(prd_record["path"]))
    run_dir = validate_run_dir(topic_dir, manifest_path.parent)
    artifact_path = validate_artifact_path(run_dir, artifact_path)
    if manifest_path.resolve().parent != run_dir:
        raise ValueError("冻结清单必须位于当前 topic 的 tmp run 目录")
    artifact_name = artifact_path.name
    artifacts = manifest.get("artifacts", [])
    if artifact_path.exists() and artifact_name not in artifacts:
        raise ValueError(f"拒绝覆盖非本次运行产物：{artifact_name}")
    if artifact_name not in artifacts:
        manifest["artifacts"] = list(artifacts) + [artifact_name]
        manifest["manifest_sha256"] = _manifest_hash(manifest)
        write_json(manifest_path, manifest)


def _claim_if_run_artifact(artifact_path: Path) -> None:
    manifest_path = artifact_path.parent / MANIFEST_NAME
    if manifest_path.is_file():
        _claim_artifact(manifest_path, artifact_path)
    else:
        raise ValueError("Design 临时证据必须写入包含 design-run.json 的 topic tmp run 目录")


def _validate_manifest_location(manifest_path: Path, manifest: Mapping[str, object]) -> Path:
    root = Path(str(manifest["repo_root"])).resolve()
    record = manifest.get("prd")
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise ValueError("冻结清单缺少 PRD 路径")
    topic_dir = topic_dir_for_document(root / str(record["path"]))
    run_dir = validate_run_dir(topic_dir, manifest_path.parent)
    if manifest_path.name != MANIFEST_NAME or manifest.get("run_id") != run_dir.name:
        raise ValueError("冻结清单与 topic tmp run 目录不匹配")
    return run_dir


def _cleanup_design_run(manifest_path: Path) -> tuple[str, ...]:
    manifest = load_json(manifest_path)
    run_dir = _validate_manifest_location(manifest_path, manifest)
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("冻结清单 artifacts 格式无效")
    return cleanup_registered_run(
        run_dir.parent.parent,
        run_dir,
        MANIFEST_NAME,
        artifacts,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze = subparsers.add_parser("freeze", help="freeze PRD, instructions and Skill versions")
    freeze.add_argument("prd", type=Path)
    freeze.add_argument("--design", type=Path)
    freeze.add_argument("--run-dir", type=Path)
    freeze.add_argument("--run-id")

    evidence = subparsers.add_parser("evidence", help="create one repository evidence summary")
    evidence.add_argument("--manifest", type=Path, required=True)
    evidence.add_argument("--output", type=Path)
    evidence.add_argument("--design", type=Path)

    bind = subparsers.add_parser("bind-candidate", help="bind an existing summary to the finished Design")
    bind.add_argument("--manifest", type=Path, required=True)
    bind.add_argument("--evidence", type=Path, required=True)
    bind.add_argument("--design", type=Path, required=True)

    fresh = subparsers.add_parser("freshness", help="check frozen inputs and evidence without rescanning")
    fresh.add_argument("--manifest", type=Path, required=True)
    fresh.add_argument("--evidence", type=Path, required=True)
    fresh.add_argument("--design", type=Path)

    preflight = subparsers.add_parser("preflight", help="run the lightweight final-candidate checks")
    preflight.add_argument("design", type=Path)
    preflight.add_argument("--output", type=Path)

    cleanup = subparsers.add_parser("cleanup", help="remove only registered artifacts from a completed run")
    cleanup.add_argument("--manifest", type=Path, required=True)

    return parser


def _run_freeze(args: argparse.Namespace) -> int:
    manifest = freeze_inputs(args.prd, args.design, args.run_dir, args.run_id)
    _print_json(manifest)
    return 0


def _run_evidence(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    _validate_manifest_location(args.manifest, manifest)
    errors = frozen_input_errors(manifest)
    if errors:
        _print_errors(errors)
        return 1
    root = Path(str(manifest["repo_root"]))
    prd = root / str(manifest["prd"]["path"])
    design = args.design or _manifest_design_path(manifest)
    summary = build_evidence_summary(prd, design, manifest)
    output = args.output or args.manifest.with_name(EVIDENCE_NAME)
    _claim_artifact(args.manifest, output)
    write_json(output, summary)
    _print_json(summary)
    return 0


def _run_bind_candidate(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    _validate_manifest_location(args.manifest, manifest)
    validate_artifact_path(args.evidence.parent, args.evidence)
    errors = frozen_input_errors(manifest) + validate_design(args.design)
    if errors:
        _print_errors(errors)
        return 1
    root = Path(str(manifest["repo_root"]))
    prd = root / str(manifest["prd"]["path"])
    summary = bind_evidence_candidate(args.evidence, prd, args.design, str(manifest["run_id"]))
    _print_json(summary)
    return 0


def _manifest_design_path(manifest: Mapping[str, object]) -> Path | None:
    design_record = manifest.get("design")
    if isinstance(design_record, dict) and design_record.get("path"):
        return Path(str(manifest["repo_root"])) / str(design_record["path"])
    return None


def _run_freshness(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    _validate_manifest_location(args.manifest, manifest)
    validate_artifact_path(args.evidence.parent, args.evidence)
    root = Path(str(manifest["repo_root"]))
    prd = root / str(manifest["prd"]["path"])
    design = args.design or _manifest_design_path(manifest)
    errors = frozen_input_errors(manifest)
    errors.extend(evidence_staleness_errors(load_json(args.evidence), manifest, prd, design))
    return _finish_check(errors, "Design 输入与证据新鲜度：通过")


def _run_preflight(args: argparse.Namespace) -> int:
    errors = validate_design(args.design)
    check = {"status": "passed" if not errors else "blocked", "design": str(args.design), "errors": errors}
    if args.output:
        _claim_if_run_artifact(args.output)
        write_json(args.output, check)
    _print_json(check)
    return 0 if not errors else 1


def _run_cleanup(args: argparse.Namespace) -> int:
    removed = _cleanup_design_run(args.manifest)
    print(json.dumps({"status": "cleaned", "removed": removed}, ensure_ascii=False, indent=2))
    return 0


def _finish_check(errors: Iterable[str], success_message: str) -> int:
    unique_errors = sorted(set(errors))
    if unique_errors:
        _print_errors(unique_errors)
        return 1
    print(success_message)
    return 0


def _print_errors(errors: Iterable[str]) -> None:
    for error in errors:
        print(f"错误：{error}", file=sys.stderr)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        handlers = {
            "freeze": _run_freeze,
            "evidence": _run_evidence,
            "bind-candidate": _run_bind_candidate,
            "freshness": _run_freshness,
            "preflight": _run_preflight,
            "cleanup": _run_cleanup,
        }
        return handlers[args.command](args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Design 运行协调失败：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
