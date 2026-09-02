#!/usr/bin/env python3
"""Verify changed production Java lines with Maven/Gradle JaCoCo reports."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE
except ImportError:  # pragma: no cover - supports package execution
    from .quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE


UNMEASURABLE = 2
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class ChangedSource:
    path: str
    lines: frozenset[int]


@dataclass(frozen=True)
class LineCoverage:
    covered: int
    missed: int
    branch_covered: int
    branch_missed: int


@dataclass(frozen=True)
class SourceCoverage:
    key: str
    lines: Mapping[int, LineCoverage]


@dataclass(frozen=True)
class CoverageBuild:
    arguments: tuple[str, ...]
    test_tasks: tuple[str, ...]
    report_tasks: tuple[str, ...]


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
    missed_lines: tuple[str, ...] = ()
    partial_branch_lines: tuple[str, ...] = ()

    @staticmethod
    def percentage(covered: int, total: int) -> float | None:
        return None if total == 0 else round(covered * 100 / total, 2)

    def as_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "line_percentage": self.percentage(self.line_covered, self.line_total),
            "branch_percentage": self.percentage(self.branch_covered, self.branch_total),
        }


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _is_production_java(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lower().strip("/")
    excluded = ("/src/test/", "/test/", "/target/", "/build/", "/generated/", "/generated-sources/")
    return normalized.endswith(".java") and not any(item in normalized for item in excluded)


def changed_sources(repo: Path, base: str, requested: Sequence[str] = ()) -> tuple[ChangedSource, ...]:
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--"])
    changed: dict[str, set[int]] = {}
    path: str | None = None
    line_number = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        match = HUNK.match(line)
        if match:
            line_number = int(match.group(1))
            continue
        if not path or not line_number or line.startswith("\\"):
            continue
        if line.startswith("+"):
            if _is_production_java(path):
                changed.setdefault(path, set()).add(line_number)
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    for raw in _run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines():
        source = repo / raw
        if _is_production_java(raw) and source.is_file():
            changed[raw] = set(range(1, len(source.read_text(encoding="utf-8").splitlines()) + 1))
    if requested:
        selected = {Path(path).as_posix().lstrip("./") for path in requested}
        changed = {path: lines for path, lines in changed.items() if path in selected}
    return tuple(ChangedSource(path, frozenset(lines)) for path, lines in sorted(changed.items()))


def _integer(element: ElementTree.Element, name: str) -> int:
    try:
        return int(element.attrib.get(name, "0"))
    except ValueError:
        return 0


def _report_module(repo: Path, report: Path) -> str:
    try:
        parts = report.resolve().relative_to(repo.resolve()).parts
    except ValueError:
        return ""
    indexes = [index for index, part in enumerate(parts) if part in {"target", "build"}]
    return "/".join(parts[: min(indexes)]) if indexes else ""


def parse_report(report: Path, prefix: str = "") -> dict[str, SourceCoverage]:
    root = ElementTree.parse(report).getroot()
    result: dict[str, SourceCoverage] = {}
    for package in root.findall(".//package"):
        package_name = package.attrib.get("name", "").strip("/")
        for sourcefile in package.findall("sourcefile"):
            source_name = sourcefile.attrib.get("name", "")
            key = f"{package_name}/{source_name}" if package_name else source_name
            if prefix:
                key = f"{prefix}/{key}"
            lines = {
                _integer(line, "nr"): LineCoverage(
                    _integer(line, "ci"),
                    _integer(line, "mi"),
                    _integer(line, "cb"),
                    _integer(line, "mb"),
                )
                for line in sourcefile.findall("line")
            }
            result[key] = SourceCoverage(key, lines)
    return result


def merge_reports(repo: Path, reports: Iterable[Path]) -> dict[str, SourceCoverage]:
    merged: dict[str, SourceCoverage] = {}
    for report in reports:
        for key, source in parse_report(report, _report_module(repo, report)).items():
            previous = merged.get(key)
            if previous is None:
                merged[key] = source
                continue
            lines = dict(previous.lines)
            for number, coverage in source.lines.items():
                current = lines.get(number)
                lines[number] = coverage if current is None else LineCoverage(
                    max(current.covered, coverage.covered),
                    min(current.missed, coverage.missed),
                    max(current.branch_covered, coverage.branch_covered),
                    min(current.branch_missed, coverage.branch_missed),
                )
            merged[key] = SourceCoverage(key, lines)
    return merged


def _match_source(path: str, sources: Mapping[str, SourceCoverage]) -> SourceCoverage | None:
    normalized = path.replace("\\", "/")
    source_relative = re.sub(r"/src/(?:main/)?java/", "/", "/" + normalized).lstrip("/")
    matches = [source for key, source in sources.items() if normalized.endswith(key) or source_relative.endswith(key)]
    if len(matches) == 1:
        return matches[0]
    basename = Path(normalized).name
    matches = [source for key, source in sources.items() if Path(key).name == basename]
    return matches[0] if len(matches) == 1 else None


def calculate(
    changed: Sequence[ChangedSource],
    sources: Mapping[str, SourceCoverage],
    line_threshold: float,
    branch_threshold: float,
) -> CoverageResult:
    line_covered = line_total = branch_covered = branch_total = 0
    missing: list[str] = []
    missed_lines: list[str] = []
    partial_branch_lines: list[str] = []
    for item in changed:
        source = _match_source(item.path, sources)
        if source is None:
            missing.append(item.path)
            continue
        for number in item.lines:
            coverage = source.lines.get(number)
            if coverage is None or coverage.covered + coverage.missed == 0:
                continue
            line_total += 1
            line_covered += int(coverage.covered > 0)
            if coverage.covered == 0:
                missed_lines.append(f"{item.path}:{number}")
            branch_total += coverage.branch_covered + coverage.branch_missed
            branch_covered += coverage.branch_covered
            if coverage.branch_missed:
                total = coverage.branch_covered + coverage.branch_missed
                partial_branch_lines.append(
                    f"{item.path}:{number} ({coverage.branch_covered}/{total})"
                )
    if missing:
        status = "unmeasurable"
    elif line_total == 0:
        status = "not_applicable"
    else:
        line_passed = line_covered * 100 >= line_total * line_threshold
        branch_passed = branch_total == 0 or branch_covered * 100 >= branch_total * branch_threshold
        status = "pass" if line_passed and branch_passed else "fail"
    return CoverageResult(
        status,
        len(changed),
        sum(len(item.lines) for item in changed),
        line_covered,
        line_total,
        branch_covered,
        branch_total,
        line_threshold,
        branch_threshold,
        tuple(sorted(missing)),
        tuple(sorted(missed_lines)),
        tuple(sorted(partial_branch_lines)),
    )


def _percentage_value(raw: str) -> float:
    value = float(raw.strip().removesuffix("%"))
    return value * 100 if 0 <= value <= 1 else value


def _maven_thresholds(pom: Path) -> tuple[float | None, float | None]:
    try:
        root = ElementTree.parse(pom).getroot()
    except ElementTree.ParseError:
        return None, None
    line: float | None = None
    branch: float | None = None
    for limit in root.iter():
        if not limit.tag.endswith("limit"):
            continue
        counter = next((child.text.strip().upper() for child in limit if child.tag.endswith("counter") and child.text), "")
        minimum = next((child.text.strip() for child in limit if child.tag.endswith("minimum") and child.text), None)
        if minimum is None:
            continue
        if counter == "LINE":
            line = _percentage_value(minimum)
        elif counter == "BRANCH":
            branch = _percentage_value(minimum)
    return line, branch


def _gradle_thresholds(paths: Iterable[Path]) -> tuple[float | None, float | None]:
    line: float | None = None
    branch: float | None = None
    pattern = re.compile(
        r"counter\s*=\s*['\"](LINE|BRANCH)['\"][\s\S]{0,300}?minimum\s*=\s*([0-9.]+)",
        re.IGNORECASE,
    )
    for path in paths:
        source = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(source):
            value = _percentage_value(match.group(2))
            if match.group(1).upper() == "LINE":
                line = max(line, value) if line is not None else value
            else:
                branch = max(branch, value) if branch is not None else value
    return line, branch


def _ancestors_within(repo: Path, requested_path: str) -> Iterable[Path]:
    current = (repo / requested_path).resolve().parent
    while current == repo or repo in current.parents:
        yield current
        if current == repo:
            return
        current = current.parent


def _relevant_build_files(repo: Path, requested_paths: Sequence[str]) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    if not requested_paths:
        poms = tuple(repo.rglob("pom.xml"))
        gradle = tuple(path for name in ("build.gradle", "build.gradle.kts") for path in repo.rglob(name))
        return poms, gradle

    poms: set[Path] = set()
    gradle: set[Path] = set()
    for requested in requested_paths:
        for directory in _ancestors_within(repo, requested):
            if (pom := directory / "pom.xml").is_file():
                poms.add(pom)
            for name in ("build.gradle", "build.gradle.kts"):
                if (build := directory / name).is_file():
                    gradle.add(build)
    return tuple(sorted(poms)), tuple(sorted(gradle))


def project_thresholds(repo: Path, requested_paths: Sequence[str] = ()) -> tuple[float, float]:
    line_values: list[float] = []
    branch_values: list[float] = []
    poms, gradle_paths = _relevant_build_files(repo.resolve(), requested_paths)
    for pom in poms:
        line, branch = _maven_thresholds(pom)
        if line is not None:
            line_values.append(line)
        if branch is not None:
            branch_values.append(branch)
    line, branch = _gradle_thresholds(gradle_paths)
    if line is not None:
        line_values.append(line)
    if branch is not None:
        branch_values.append(branch)
    return (
        max(line_values) if line_values else DEFAULT_LINE_COVERAGE,
        max(branch_values) if branch_values else DEFAULT_BRANCH_COVERAGE,
    )


def _build_tool(repo: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if (repo / "mvnw").is_file() or (repo / "pom.xml").is_file():
        return "maven"
    if (repo / "gradlew").is_file() or any((repo / name).is_file() for name in ("build.gradle", "build.gradle.kts")):
        return "gradle"
    raise RuntimeError("无法识别 Maven 或 Gradle Java 项目")


def _executable(repo: Path, wrapper: str, command: str) -> list[str]:
    path = repo / wrapper
    if path.is_file():
        return [str(path)] if path.stat().st_mode & 0o111 else ["sh", str(path)]
    return [shutil.which(command) or command]


def _gradle_init_script() -> str:
    return """allprojects {
    plugins.withId('java') { apply plugin: 'jacoco' }
    afterEvaluate {
        tasks.withType(org.gradle.testing.jacoco.tasks.JacocoReport).configureEach {
            reports { xml.required = true }
        }
    }
}
"""


def _tasks(requested: Sequence[str], default: str) -> list[str]:
    return list(dict.fromkeys(requested)) or [default]


def _validate_build_arguments(tool: str, build: CoverageBuild) -> None:
    if tool != "gradle":
        return
    task_arguments = {
        "test",
        "jacocoTestReport",
    }
    duplicate_tasks = [
        argument
        for argument in build.arguments
        if argument in task_arguments or argument.startswith(":") and ":" in argument[1:]
    ]
    if duplicate_tasks:
        raise ValueError(
            "Gradle 测试或 JaCoCo task 请使用 --test-task/--jacoco-task，不要放入 --build-arg："
            + ", ".join(duplicate_tasks)
        )


def _maven_coverage_command(repo: Path, build: CoverageBuild) -> list[str]:
    return [
        *_executable(repo, "mvnw", "mvn"),
        *build.arguments,
        "org.jacoco:jacoco-maven-plugin:prepare-agent",
        *_tasks(build.test_tasks, "test"),
        *_tasks(build.report_tasks, "org.jacoco:jacoco-maven-plugin:report"),
    ]


def _gradle_coverage_command(repo: Path, build: CoverageBuild, init_script: str) -> list[str]:
    return [
        *_executable(repo, "gradlew", "gradle"),
        "--init-script",
        init_script,
        *build.arguments,
        *_tasks(build.test_tasks, "test"),
        *_tasks(build.report_tasks, "jacocoTestReport"),
    ]


def _run_coverage(repo: Path, tool: str, build: CoverageBuild) -> tuple[int, list[str]]:
    _validate_build_arguments(tool, build)
    if tool == "maven":
        command = _maven_coverage_command(repo, build)
        return subprocess.run(command, cwd=repo, check=False).returncode, command
    with tempfile.NamedTemporaryFile("w", suffix=".gradle", encoding="utf-8") as init_script:
        init_script.write(_gradle_init_script())
        init_script.flush()
        command = _gradle_coverage_command(repo, build, init_script.name)
        return subprocess.run(command, cwd=repo, check=False).returncode, command


def _discover_reports(repo: Path, not_before: float | None) -> tuple[Path, ...]:
    reports = [
        path
        for path in repo.rglob("*.xml")
        if ".git" not in path.parts
        and ("target" in path.parts or "build" in path.parts)
        and "jacoco" in path.as_posix().lower()
    ]
    if not_before is not None:
        reports = [path for path in reports if path.stat().st_mtime >= not_before]
    return tuple(sorted(set(reports)))


def _stale_sources(repo: Path, changed: Sequence[ChangedSource], reports: Sequence[Path]) -> list[str]:
    parsed = [(report.stat().st_mtime, parse_report(report, _report_module(repo, report))) for report in reports]
    stale: list[str] = []
    for item in changed:
        source_path = repo / item.path
        matching_times = [modified for modified, sources in parsed if _match_source(item.path, sources) is not None]
        if source_path.is_file() and matching_times and max(matching_times) < source_path.stat().st_mtime:
            stale.append(item.path)
    return stale


def _location_summary(locations: Sequence[str]) -> str:
    visible = locations[:20]
    remaining = len(locations) - len(visible)
    suffix = f"，另有 {remaining} 项；用 --json-output 查看完整列表" if remaining else ""
    return ", ".join(visible) + suffix


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", required=True, help="Git 基线，例如 HEAD")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="本次含可执行行为增量的生产 Java 文件；可重复",
    )
    parser.add_argument("--build-tool", choices=("auto", "maven", "gradle"), default="auto")
    parser.add_argument(
        "--build-arg",
        action="append",
        default=[],
        help="传给 Maven/Gradle 的选项或项目选择器，可重复；不能用它替换测试任务",
    )
    parser.add_argument(
        "--test-task",
        action="append",
        default=[],
        help="最终合并构建中执行的 Maven goal 或 Gradle task，可重复；默认 test",
    )
    parser.add_argument(
        "--jacoco-task",
        action="append",
        default=[],
        help="最终合并构建中执行的 JaCoCo 报告 goal/task；Gradle 模块任务需显式指定",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--report",
        action="append",
        type=Path,
        help="已有 JaCoCo XML 报告，可重复；只读取，不运行测试",
    )
    parser.add_argument("--report-not-before", type=float, help="手动报告的最早生成时间")
    mode.add_argument(
        "--run",
        action="store_true",
        help="执行最终一次相关模块测试并生成新鲜 JaCoCo 报告",
    )
    parser.add_argument("--json-output", type=Path, help="可选普通结果 JSON 文件")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    repo = args.repo.resolve()
    started = time.time()
    try:
        tool = _build_tool(repo, args.build_tool)
        line_threshold, branch_threshold = project_thresholds(repo, args.path)
        if not 0 <= line_threshold <= 100 or not 0 <= branch_threshold <= 100:
            raise ValueError("覆盖率阈值必须在 0 到 100 之间")
        if args.run:
            forbidden = re.compile(
                r"skipTests|maven\.test\.skip|test\.enabled\s*=\s*false|(?:^|\s)(?:-x|--exclude-task)(?:\s|=)",
                re.IGNORECASE,
            )
            requested_build = " ".join((*args.build_arg, *args.test_task, *args.jacoco_task))
            if forbidden.search(requested_build):
                raise ValueError("覆盖率命令不能跳过测试")
            build = CoverageBuild(
                tuple(args.build_arg),
                tuple(args.test_task),
                tuple(args.jacoco_task),
            )
            exit_code, command = _run_coverage(repo, tool, build)
            if exit_code:
                raise RuntimeError(f"覆盖率测试命令失败（退出码 {exit_code}）：{' '.join(command)}")
        changed = changed_sources(repo, args.base, args.path)
        if args.report:
            reports = tuple(path if path.is_absolute() else repo / path for path in args.report)
            reports = tuple(path for path in reports if path.is_file())
            if args.report_not_before is not None:
                reports = tuple(path for path in reports if path.stat().st_mtime >= args.report_not_before)
        else:
            reports = _discover_reports(repo, started if args.run else args.report_not_before)
        if changed and not reports:
            raise RuntimeError("未找到 JaCoCo XML 报告；请使用 --run 或 --report")
        stale = _stale_sources(repo, changed, reports)
        if stale:
            raise RuntimeError("JaCoCo 报告早于生产源文件：" + ", ".join(stale))
        result = calculate(changed, merge_reports(repo, reports) if reports else {}, line_threshold, branch_threshold)
        payload = result.as_dict()
        payload.update({"build_tool": tool, "reports": [str(path) for path in reports]})
        if args.json_output:
            output = args.json_output if args.json_output.is_absolute() else repo / args.json_output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        line = "不适用" if result.line_total == 0 else f"{CoverageResult.percentage(result.line_covered, result.line_total):.2f}%"
        branch = "不适用" if result.branch_total == 0 else f"{CoverageResult.percentage(result.branch_covered, result.branch_total):.2f}%"
        print(
            f"JaCoCo 增量覆盖率：{result.status}；行={line}（阈值 {line_threshold:.2f}%），"
            f"分支={branch}（阈值 {branch_threshold:.2f}%）"
        )
        if result.missing_sources:
            print("无法匹配报告的生产源：" + ", ".join(result.missing_sources), file=sys.stderr)
        if result.status == "fail" and result.missed_lines:
            print("未覆盖增量行：" + _location_summary(result.missed_lines), file=sys.stderr)
        if result.status == "fail" and result.partial_branch_lines:
            print("未完全覆盖的增量分支：" + _location_summary(result.partial_branch_lines), file=sys.stderr)
        if result.status in {"pass", "not_applicable"}:
            return 0
        return 1 if result.status == "fail" else UNMEASURABLE
    except (OSError, RuntimeError, ValueError, ElementTree.ParseError) as error:
        print(f"JaCoCo 增量覆盖率：无法验证：{error}", file=sys.stderr)
        return UNMEASURABLE


if __name__ == "__main__":
    raise SystemExit(main())
