#!/usr/bin/env python3
"""Run or verify JaCoCo coverage for changed production Java lines."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from candidate_contract import quality_bundle_sha256  # type: ignore[import-not-found]
from evidence_binding import evidence_sha256, file_sha256, self_bound_sha256  # type: ignore[import-not-found]
from quality_registry import MIN_BRANCH_COVERAGE, MIN_LINE_COVERAGE  # type: ignore[import-not-found]
from pretty_tmp import (  # type: ignore[import-not-found]
    is_pretty_tmp_path,
    topic_dir_for_document,
    validate_artifact_path,
    validate_run_dir,
)


DEFAULT_LINE_THRESHOLD = MIN_LINE_COVERAGE
DEFAULT_BRANCH_THRESHOLD = MIN_BRANCH_COVERAGE
UNMEASURABLE_EXIT = 2
HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
STATUS_LABELS = {
    "pass": "通过",
    "fail": "未达标",
    "unmeasurable": "无法验证",
    "not_applicable": "不适用",
}


@dataclass(frozen=True)
class ChangedSource:
    path: str
    lines: frozenset[int]


@dataclass(frozen=True)
class LineCoverage:
    instruction_covered: int
    instruction_missed: int
    branch_covered: int
    branch_missed: int


@dataclass(frozen=True)
class SourceCoverage:
    source_key: str
    lines: Mapping[int, LineCoverage]


@dataclass(frozen=True)
class CoverageResult:
    status: str
    changed_files: int
    changed_lines: int
    line_covered: int
    line_total: int
    branch_covered: int
    branch_total: int
    line_threshold: float
    branch_threshold: float
    missing_sources: tuple[str, ...]

    @property
    def line_percentage(self) -> float | None:
        return _percentage(self.line_covered, self.line_total)

    @property
    def branch_percentage(self) -> float | None:
        return _percentage(self.branch_covered, self.branch_total)

    def as_dict(self) -> dict[str, object]:
        coverage_payload = asdict(self)
        coverage_payload["line_percentage"] = self.line_percentage
        coverage_payload["branch_percentage"] = self.branch_percentage
        coverage_payload["status_label"] = STATUS_LABELS[self.status]
        coverage_payload["passed"] = self.status in {"pass", "not_applicable"}
        return coverage_payload


@dataclass(frozen=True)
class CoverageEvidenceRequest:
    result: CoverageResult
    reports: Sequence[Path]
    source_hashes: Mapping[str, str]
    design_sha256: str
    start_head: str
    execution_matrix_sha256: str
    resolver_sha256: str
    shared_bundle_sha256: str
    json_output: Path | None
    quality_candidate_sha256: str


def _percentage(covered: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(covered * 100 / total, 2)


def _is_production_java(path: str) -> bool:
    if is_pretty_tmp_path(path):
        return False
    normalized = f"/{path.replace(chr(92), '/').lower().lstrip('/')}"
    excluded = (
        "/src/test/",
        "/test/",
        "/target/",
        "/build/",
        "/generated/",
        "/generated-sources/",
    )
    return normalized.endswith(".java") and not any(item in normalized for item in excluded)


def parse_changed_diff(diff: str) -> dict[str, frozenset[int]]:
    """Parse changed new-side line numbers from a zero-context Git diff."""
    changed: dict[str, set[int]] = {}
    current_path: str | None = None
    new_line = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
            continue
        hunk = HUNK_PATTERN.match(line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if current_path is None or new_line == 0 or line.startswith("\\"):
            continue
        if line.startswith("+"):
            if _is_production_java(current_path):
                changed.setdefault(current_path, set()).add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        else:
            new_line += 1
    return {path: frozenset(lines) for path, lines in changed.items()}


def _run_git(repo: Path, arguments: Sequence[str]) -> str:
    command = ["git", "-C", str(repo), *arguments]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "git command failed"
        raise RuntimeError(f"{' '.join(command)}: {detail}")
    return completed.stdout


def _untracked_sources(repo: Path) -> dict[str, frozenset[int]]:
    output = _run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    sources: dict[str, frozenset[int]] = {}
    for relative_path in output.splitlines():
        if is_pretty_tmp_path(relative_path):
            continue
        if not _is_production_java(relative_path):
            continue
        source_path = repo / relative_path
        line_count = len(source_path.read_text(encoding="utf-8").splitlines())
        sources[relative_path] = frozenset(range(1, line_count + 1))
    return sources


def collect_changed_sources(repo: Path, base: str) -> tuple[ChangedSource, ...]:
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--"])
    changed = parse_changed_diff(diff)
    changed.update(_untracked_sources(repo))
    return tuple(ChangedSource(path, lines) for path, lines in sorted(changed.items()))


def load_changed_manifest(manifest: Path) -> tuple[ChangedSource, ...]:
    """Load execution-attributed changed lines from a temporary JSON manifest."""
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("changed manifest must be a JSON object")
    sources: list[ChangedSource] = []
    for path, line_numbers in payload.items():
        if not isinstance(path, str) or not isinstance(line_numbers, list):
            raise ValueError("changed manifest values must be path-to-line-list entries")
        if not _is_production_java(path):
            continue
        if any(not isinstance(line, int) or line < 1 for line in line_numbers):
            raise ValueError(f"invalid line number for {path}")
        if not line_numbers:
            raise ValueError(f"changed manifest production Java entry must contain changed lines: {path}")
        sources.append(ChangedSource(path, frozenset(line_numbers)))
    return tuple(sorted(sources, key=lambda source: source.path))


def _integer_attribute(element: ElementTree.Element, name: str) -> int:
    try:
        return int(element.attrib.get(name, "0"))
    except ValueError:
        return 0


def _source_key(package_name: str, source_name: str) -> str:
    package = package_name.strip("/")
    return f"{package}/{source_name}" if package else source_name


def parse_jacoco_report(
    report: Path,
    source_prefix: str = "",
) -> dict[str, SourceCoverage]:
    root = ElementTree.parse(report).getroot()
    sources: dict[str, SourceCoverage] = {}
    for package in root.findall(".//package"):
        package_name = package.attrib.get("name", "")
        for sourcefile in package.findall("sourcefile"):
            source_name = sourcefile.attrib.get("name", "")
            key = _source_key(package_name, source_name)
            key = f"{source_prefix}/{key}" if source_prefix else key
            lines = {
                _integer_attribute(line, "nr"): LineCoverage(
                    _integer_attribute(line, "ci"),
                    _integer_attribute(line, "mi"),
                    _integer_attribute(line, "cb"),
                    _integer_attribute(line, "mb"),
                )
                for line in sourcefile.findall("line")
            }
            sources[key] = SourceCoverage(key, lines)
    return sources


def _report_module(repo: Path, report: Path) -> str:
    try:
        relative_parts = report.resolve().relative_to(repo.resolve()).parts
    except ValueError:
        return ""
    build_indexes = [
        index
        for index, part in enumerate(relative_parts)
        if part in {"target", "build"}
    ]
    if not build_indexes:
        return ""
    return "/".join(relative_parts[: build_indexes[0]])


def merge_reports(
    reports: Iterable[Path],
    repo: Path | None = None,
) -> dict[str, SourceCoverage]:
    merged: dict[str, SourceCoverage] = {}
    for report in reports:
        prefix = _report_module(repo, report) if repo else ""
        for key, source in parse_jacoco_report(report, prefix).items():
            existing = merged.get(key)
            if existing is None:
                merged[key] = source
                continue
            merged[key] = SourceCoverage(key, _merge_line_maps(existing.lines, source.lines))
    return merged


def _merge_line_maps(
    first: Mapping[int, LineCoverage], second: Mapping[int, LineCoverage]
) -> dict[int, LineCoverage]:
    merged = dict(first)
    for line_number, coverage in second.items():
        previous = merged.get(line_number)
        if previous is None:
            merged[line_number] = coverage
            continue
        merged[line_number] = LineCoverage(
            max(previous.instruction_covered, coverage.instruction_covered),
            min(previous.instruction_missed, coverage.instruction_missed),
            max(previous.branch_covered, coverage.branch_covered),
            min(previous.branch_missed, coverage.branch_missed),
        )
    return merged


def _match_source(path: str, sources: Mapping[str, SourceCoverage]) -> SourceCoverage | None:
    normalized = path.replace("\\", "/")
    source_relative = re.sub(r"/(?:src/(?:main|test)/java|src)/", "/", normalized)
    suffix_matches = [
        source
        for key, source in sources.items()
        if normalized.endswith(key) or source_relative.endswith(key)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    basename = Path(normalized).name
    basename_matches = [source for key, source in sources.items() if Path(key).name == basename]
    return basename_matches[0] if len(basename_matches) == 1 else None


def calculate_coverage(
    changed_sources: Sequence[ChangedSource],
    sources: Mapping[str, SourceCoverage],
    line_threshold: float = DEFAULT_LINE_THRESHOLD,
    branch_threshold: float = DEFAULT_BRANCH_THRESHOLD,
) -> CoverageResult:
    line_covered, line_total, branch_covered, branch_total, missing = _coverage_totals(
        changed_sources, sources
    )
    changed_line_count = sum(len(source.lines) for source in changed_sources)
    status = _coverage_status(
        missing,
        line_covered,
        line_total,
        branch_covered,
        branch_total,
        line_threshold,
        branch_threshold,
    )
    return CoverageResult(
        status,
        len(changed_sources),
        changed_line_count,
        line_covered,
        line_total,
        branch_covered,
        branch_total,
        line_threshold,
        branch_threshold,
        tuple(sorted(missing)),
    )


def _coverage_totals(
    changed_sources: Sequence[ChangedSource], sources: Mapping[str, SourceCoverage]
) -> tuple[int, int, int, int, tuple[str, ...]]:
    line_covered = 0
    line_total = 0
    branch_covered = 0
    branch_total = 0
    missing: list[str] = []
    for changed in changed_sources:
        source = _match_source(changed.path, sources)
        if source is None:
            missing.append(changed.path)
            continue
        source_totals = _source_totals(changed.lines, source)
        line_covered += source_totals[0]
        line_total += source_totals[1]
        branch_covered += source_totals[2]
        branch_total += source_totals[3]
    return line_covered, line_total, branch_covered, branch_total, tuple(sorted(missing))


def _source_totals(
    changed_lines: frozenset[int], source: SourceCoverage
) -> tuple[int, int, int, int]:
    line_covered = 0
    line_total = 0
    branch_covered = 0
    branch_total = 0
    for line_number in changed_lines:
        coverage = source.lines.get(line_number)
        if coverage is None or coverage.instruction_covered + coverage.instruction_missed == 0:
            continue
        line_total += 1
        line_covered += int(coverage.instruction_covered > 0)
        branch_total += coverage.branch_covered + coverage.branch_missed
        branch_covered += coverage.branch_covered
    return line_covered, line_total, branch_covered, branch_total


def _coverage_status(
    missing: Sequence[str],
    line_covered: int,
    line_total: int,
    branch_covered: int,
    branch_total: int,
    line_threshold: float,
    branch_threshold: float,
) -> str:
    if missing:
        return "unmeasurable"
    if line_total == 0:
        return "not_applicable"
    line_passes = line_covered * 100 >= line_total * line_threshold
    branch_passes = branch_total == 0 or branch_covered * 100 >= branch_total * branch_threshold
    return "pass" if line_passes and branch_passes else "fail"


def _find_build_tool(repo: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if (repo / "mvnw").exists() or (repo / "pom.xml").exists():
        return "maven"
    if (repo / "gradlew").exists() or any((repo / name).exists() for name in ("build.gradle", "build.gradle.kts")):
        return "gradle"
    raise RuntimeError("无法自动识别 Maven 或 Gradle 构建项目")


def _executable(repo: Path, wrapper: str, system_command: str) -> str:
    wrapper_path = repo / wrapper
    if wrapper_path.exists():
        return str(wrapper_path)
    return shutil.which(system_command) or system_command


def _gradle_init_script() -> str:
    return """allprojects {\n    plugins.withId('java') {\n        apply plugin: 'jacoco'\n    }\n}\n"""


def _run_build_command(repo: Path, command: list[str]) -> tuple[int, list[str]]:
    completed = subprocess.run(command, cwd=repo, check=False)
    return completed.returncode, command


def _maven_coverage_command(repo: Path, build_arguments: Sequence[str]) -> list[str]:
    return [
        _executable(repo, "mvnw", "mvn"),
        *build_arguments,
        "org.jacoco:jacoco-maven-plugin:prepare-agent",
        "test",
        "org.jacoco:jacoco-maven-plugin:report",
    ]


def _gradle_coverage_command(
    repo: Path, build_arguments: Sequence[str], init_script: Path
) -> list[str]:
    return [
        _executable(repo, "gradlew", "gradle"),
        "--no-daemon",
        "--init-script",
        str(init_script),
        *build_arguments,
        "test",
        "jacocoTestReport",
    ]


def run_coverage_build(
    repo: Path,
    build_tool: str,
    build_arguments: Sequence[str],
    temporary_dir: Path | None = None,
) -> tuple[int, list[str]]:
    if build_tool == "maven":
        return _run_build_command(repo, _maven_coverage_command(repo, build_arguments))
    if temporary_dir is None:
        raise ValueError("Gradle coverage requires a topic tmp run directory")
    temporary_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".gradle", dir=temporary_dir, encoding="utf-8") as init_file:
        init_file.write(_gradle_init_script())
        init_file.flush()
        command = _gradle_coverage_command(repo, build_arguments, Path(init_file.name))
        return _run_build_command(repo, command)


def discover_reports(repo: Path) -> tuple[Path, ...]:
    reports = []
    for report in repo.rglob("jacoco.xml"):
        if ".git" not in report.parts and ("target" in report.parts or "build" in report.parts):
            reports.append(report)
    return tuple(sorted(set(reports)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="目标仓库根目录")
    parser.add_argument("--design", type=Path, required=True, help="当前批准的 Design")
    parser.add_argument("--execution-matrix", type=Path, required=True)
    parser.add_argument("--resolver", type=Path, required=True)
    parser.add_argument("--base", required=True, help="记录在 Apply 状态中的起始 HEAD")
    parser.add_argument(
        "--changed-manifest",
        type=Path,
        help="可选 TASK 归因；必须与 Git 推导的生产 Java 增量完全一致",
    )
    parser.add_argument("--report", action="append", type=Path, help="JaCoCo XML；可重复传入")
    parser.add_argument("--run", action="store_true", help="先运行通用 Maven/Gradle 覆盖率任务")
    parser.add_argument("--build-tool", choices=("auto", "maven", "gradle"), default="auto")
    parser.add_argument("--build-arg", action="append", default=[], help="传给构建工具的参数；可重复传入")
    parser.add_argument("--line-threshold", type=float, default=DEFAULT_LINE_THRESHOLD)
    parser.add_argument("--branch-threshold", type=float, default=DEFAULT_BRANCH_THRESHOLD)
    parser.add_argument("--json-output", type=Path, help="可选 JSON 结果路径")
    parser.add_argument(
        "--report-not-before",
        type=float,
        help="未使用 --run 时，JaCoCo 报告不得早于此 Unix 时间",
    )
    parser.add_argument("--quality-candidate-sha256", required=True)
    return parser


def _resolve_reports(
    repo: Path,
    report_arguments: Sequence[Path] | None,
    not_before: float,
) -> tuple[Path, ...]:
    if report_arguments:
        reports = tuple(path if path.is_absolute() else repo / path for path in report_arguments)
    else:
        reports = discover_reports(repo)
    return tuple(report for report in reports if report.is_file() and report.stat().st_mtime >= not_before)


def _render_text(result: CoverageResult) -> str:
    line = "n/a" if result.line_percentage is None else f"{result.line_percentage:.2f}%"
    branch = "n/a" if result.branch_percentage is None else f"{result.branch_percentage:.2f}%"
    return (
        f"增量覆盖率：{STATUS_LABELS[result.status]}；"
        f"行={line}（阈值 {result.line_threshold:.2f}%），"
        f"分支={branch}（阈值 {result.branch_threshold:.2f}%），"
        f"增量文件={result.changed_files}，增量行={result.changed_lines}"
    )


def _write_json(output_path: Path | None, payload: Mapping[str, object]) -> None:
    if output_path:
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _emit_result(request: CoverageEvidenceRequest) -> int:
    payload = request.result.as_dict()
    payload["reports"] = [str(report) for report in request.reports]
    payload["report_sha256"] = {
        str(report): file_sha256(report)
        for report in request.reports
    }
    payload["source_sha256"] = dict(sorted(request.source_hashes.items()))
    payload["design_sha256"] = request.design_sha256
    payload["start_head"] = request.start_head
    payload["execution_matrix_sha256"] = request.execution_matrix_sha256
    payload["resolver_sha256"] = request.resolver_sha256
    payload["shared_bundle_sha256"] = request.shared_bundle_sha256
    payload["quality_candidate_sha256"] = request.quality_candidate_sha256
    payload["scope"] = "final"
    payload["generated_at"] = time.time()
    payload["candidate_sha256"] = self_bound_sha256(payload)
    payload["evidence_sha256"] = evidence_sha256(payload)
    print(_render_text(coverage_result))
    _write_json(request.json_output, payload)
    if request.result.status == "unmeasurable":
        return UNMEASURABLE_EXIT
    return 0 if request.result.status in {"pass", "not_applicable"} else 1


def _run_requested_build(args: argparse.Namespace, repo: Path, temporary_dir: Path | None) -> None:
    if not args.run:
        return
    _reject_test_skipping(args.build_arg)
    build_tool = _find_build_tool(repo, args.build_tool)
    build_exit, command = run_coverage_build(repo, build_tool, args.build_arg, temporary_dir)
    if build_exit != 0:
        raise RuntimeError(f"Coverage build failed ({build_exit}): {shlex.join(command)}")


def _load_changed_sources(
    args: argparse.Namespace,
    repo: Path,
    start_head: str,
) -> tuple[ChangedSource, ...]:
    actual = collect_changed_sources(repo, start_head)
    if not args.changed_manifest:
        return actual
    declared = load_changed_manifest(args.changed_manifest)
    actual_map = {source.path: source.lines for source in actual}
    declared_map = {source.path: source.lines for source in declared}
    if declared_map != actual_map:
        raise ValueError(
            "changed manifest production Java scope must exactly match the Git diff: "
            f"declared={sorted(declared_map)}, actual={sorted(actual_map)}"
        )
    return actual


def _source_hashes(repo: Path, sources: Sequence[ChangedSource]) -> dict[str, str]:
    return {
        source.path: file_sha256(repo / source.path)
        for source in sources
        if (repo / source.path).is_file()
    }


def _stale_sources(
    repo: Path,
    changed_sources: Sequence[ChangedSource],
    reports: Sequence[Path],
) -> list[str]:
    parsed_reports = [
        (report.stat().st_mtime, parse_jacoco_report(report, _report_module(repo, report)))
        for report in reports
    ]
    stale = []
    for changed in changed_sources:
        source_path = repo / changed.path
        matching_mtimes = [
            modified_at
            for modified_at, sources in parsed_reports
            if _match_source(changed.path, sources) is not None
        ]
        if source_path.is_file() and matching_mtimes and max(matching_mtimes) < source_path.stat().st_mtime:
            stale.append(changed.path)
    return stale


def _reject_test_skipping(build_arguments: Sequence[str]) -> None:
    forbidden = re.compile(
        r"skipTests|maven\.test\.skip|test\.enabled\s*=\s*false|"
        r"(?:^|\s)(?:-x|--exclude-task)(?:\s|=)",
        re.IGNORECASE,
    )
    rendered = " ".join(build_arguments)
    if forbidden.search(rendered):
        raise ValueError("coverage build arguments must not skip or exclude tests")


def _validate_thresholds(line_threshold: float, branch_threshold: float) -> None:
    if not MIN_LINE_COVERAGE <= line_threshold <= 100:
        raise ValueError(f"line threshold must be between {MIN_LINE_COVERAGE:g} and 100")
    if not MIN_BRANCH_COVERAGE <= branch_threshold <= 100:
        raise ValueError(f"branch threshold must be between {MIN_BRANCH_COVERAGE:g} and 100")


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    repo = args.repo.resolve()
    try:
        design_path = args.design if args.design.is_absolute() else repo / args.design
        topic_dir = topic_dir_for_document(design_path)
        run_dir = None
        if args.json_output is not None:
            output_path = args.json_output if args.json_output.is_absolute() else repo / args.json_output
            run_dir = validate_run_dir(topic_dir, output_path.parent)
            args.json_output = validate_artifact_path(run_dir, output_path)
        if args.changed_manifest is not None:
            manifest_path = (
                args.changed_manifest
                if args.changed_manifest.is_absolute()
                else repo / args.changed_manifest
            )
            if run_dir is None:
                run_dir = validate_run_dir(topic_dir, manifest_path.parent)
            validate_artifact_path(run_dir, manifest_path)
            args.changed_manifest = manifest_path
        matrix_path = args.execution_matrix if args.execution_matrix.is_absolute() else repo / args.execution_matrix
        resolver_path = args.resolver if args.resolver.is_absolute() else repo / args.resolver
        if run_dir is None:
            run_dir = validate_run_dir(topic_dir, matrix_path.parent)
        validate_artifact_path(run_dir, matrix_path)
        validate_artifact_path(run_dir, resolver_path)
        design_sha256 = file_sha256(design_path)
        matrix_sha256 = file_sha256(matrix_path)
        resolver_sha256 = file_sha256(resolver_path)
        shared_bundle_sha256 = quality_bundle_sha256()
        start_head = _run_git(repo, ["rev-parse", "--verify", f"{args.base}^{{commit}}"]).strip()
        _validate_thresholds(args.line_threshold, args.branch_threshold)
        if not args.run and args.report_not_before is None:
            raise ValueError("--report-not-before is required unless --run is used")
        report_not_before = time.time() if args.run else args.report_not_before
        assert report_not_before is not None
        _run_requested_build(args, repo, run_dir)
        reports = _resolve_reports(repo, args.report, report_not_before)
        changed_sources = _load_changed_sources(args, repo, start_head)
        source_hashes = _source_hashes(repo, changed_sources)
        if not changed_sources:
            coverage_result = calculate_coverage((), {}, args.line_threshold, args.branch_threshold)
            return _emit_result(CoverageEvidenceRequest(
                coverage_result, (), source_hashes, design_sha256, start_head,
                matrix_sha256, resolver_sha256, shared_bundle_sha256,
                args.json_output, args.quality_candidate_sha256,
            ))
        if not reports:
            raise RuntimeError("未找到 JaCoCo XML 报告；请使用 --report 或 --run")
        stale_sources = _stale_sources(repo, changed_sources, reports)
        if stale_sources:
            raise RuntimeError(f"JaCoCo 报告早于生产源码：{', '.join(stale_sources)}")
        sources = merge_reports(reports, repo)
        coverage_result = calculate_coverage(
            changed_sources,
            sources,
            args.line_threshold,
            args.branch_threshold,
        )
        return _emit_result(CoverageEvidenceRequest(
            coverage_result, reports, source_hashes, design_sha256, start_head,
            matrix_sha256, resolver_sha256, shared_bundle_sha256,
            args.json_output, args.quality_candidate_sha256,
        ))
    except (OSError, RuntimeError, ValueError, ElementTree.ParseError) as error:
        print(f"覆盖率验证无法验证：{error}", file=sys.stderr)
        return UNMEASURABLE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
