#!/usr/bin/env python3
"""Check JaCoCo coverage only for production Java lines added in a Git diff."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple
import xml.etree.ElementTree as ET


HUNK_PATTERN = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE
)


@dataclass(frozen=True)
class LineCoverage:
    missed_instructions: int
    covered_instructions: int
    missed_branches: int
    covered_branches: int

    @property
    def executable(self) -> bool:
        return self.missed_instructions + self.covered_instructions > 0

    @property
    def covered(self) -> bool:
        return self.covered_instructions > 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check JaCoCo coverage for added src/main/java lines only."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--file", action="append", dest="files")
    parser.add_argument("--line-threshold", type=int, default=90)
    parser.add_argument("--branch-threshold", type=int, default=80)
    return parser.parse_args(argv)


def is_production_java(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(".java") and (
        normalized.startswith("src/main/java/") or "/src/main/java/" in normalized
    )


def parse_added_lines(diff_text: str) -> Dict[str, Set[int]]:
    added: Dict[str, Set[int]] = {}
    current_path = None
    current_chunks: List[str] = []

    def flush() -> None:
        if current_path is None or not is_production_java(current_path):
            return
        line_numbers = added.setdefault(current_path, set())
        for chunk in current_chunks:
            match = HUNK_PATTERN.match(chunk)
            if not match:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            line_numbers.update(range(start, start + count))

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            flush()
            raw_path = line[4:]
            current_path = None if raw_path == "/dev/null" else raw_path.removeprefix("b/")
            current_chunks = []
        elif line.startswith("@@ "):
            current_chunks.append(line)
    flush()
    return {path: lines for path, lines in added.items() if lines}


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def added_production_lines(repo: Path, base: str) -> Dict[str, Set[int]]:
    diff = git_output(
        repo,
        "-c",
        "core.quotepath=false",
        "diff",
        "--find-renames",
        "--unified=0",
        "--no-color",
        base,
        "--",
    )
    added = parse_added_lines(diff)
    untracked = git_output(
        repo, "ls-files", "--others", "--exclude-standard"
    ).splitlines()
    for relative_path in untracked:
        if not is_production_java(relative_path):
            continue
        path = repo / relative_path
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        added[relative_path] = set(range(1, line_count + 1))
    return added


def infer_source_path(repo: Path, report: Path, package: str, filename: str) -> str:
    relative_source = Path(*package.split("/")) / filename if package else Path(filename)
    resolved_repo = repo.resolve()
    for ancestor in report.resolve().parents:
        source_root = ancestor / "src" / "main" / "java"
        if source_root.is_dir():
            candidate = source_root / relative_source
            try:
                return candidate.resolve().relative_to(resolved_repo).as_posix()
            except ValueError:
                break
        if ancestor == resolved_repo:
            break
    return (Path("src/main/java") / relative_source).as_posix()


def parse_reports(
    repo: Path, reports: Iterable[Path]
) -> Dict[str, Dict[int, LineCoverage]]:
    coverage: Dict[str, Dict[int, LineCoverage]] = {}
    for report in reports:
        if not report.is_file():
            raise RuntimeError(f"JaCoCo report not found: {report}")
        root = ET.parse(report).getroot()
        for package in root.findall(".//package"):
            package_name = package.attrib.get("name", "")
            for source_file in package.findall("sourcefile"):
                source_path = infer_source_path(
                    repo, report, package_name, source_file.attrib["name"]
                )
                target = coverage.setdefault(source_path, {})
                for line in source_file.findall("line"):
                    line_number = int(line.attrib["nr"])
                    current = LineCoverage(
                        missed_instructions=int(line.attrib.get("mi", "0")),
                        covered_instructions=int(line.attrib.get("ci", "0")),
                        missed_branches=int(line.attrib.get("mb", "0")),
                        covered_branches=int(line.attrib.get("cb", "0")),
                    )
                    previous = target.get(line_number)
                    if previous is None:
                        target[line_number] = current
                    else:
                        target[line_number] = LineCoverage(
                            min(previous.missed_instructions, current.missed_instructions),
                            max(previous.covered_instructions, current.covered_instructions),
                            min(previous.missed_branches, current.missed_branches),
                            max(previous.covered_branches, current.covered_branches),
                        )
    return coverage


def resolve_coverage_path(
    changed_path: str, coverage: Mapping[str, Dict[int, LineCoverage]]
) -> str:
    if changed_path in coverage:
        return changed_path
    marker = "src/main/java/"
    suffix = changed_path.split(marker, 1)[-1]
    matches = [path for path in coverage if path.endswith(marker + suffix) or path == marker + suffix]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"no JaCoCo source mapping for added Java file: {changed_path}")
    raise RuntimeError(f"ambiguous JaCoCo source mapping for added Java file: {changed_path}")


def percent(covered: int, total: int) -> str:
    return "N/A" if total == 0 else f"{covered * 100 / total:.2f}%"


def check(args: argparse.Namespace) -> Tuple[List[str], List[str]]:
    if not 0 <= args.line_threshold <= 100 or not 0 <= args.branch_threshold <= 100:
        raise RuntimeError("coverage thresholds must be between 0 and 100")
    repo = args.repo.resolve()
    changed = added_production_lines(repo, args.base)
    if args.files:
        allowed = {Path(path).as_posix() for path in args.files}
        changed = {path: lines for path, lines in changed.items() if path in allowed}
    coverage = parse_reports(repo, args.report)

    executable_lines = 0
    covered_lines = 0
    total_branches = 0
    covered_branches = 0
    missed_locations: List[str] = []
    for changed_path, changed_lines in sorted(changed.items()):
        coverage_path = resolve_coverage_path(changed_path, coverage)
        file_coverage = coverage[coverage_path]
        for line_number in sorted(changed_lines):
            line = file_coverage.get(line_number)
            if line is None or not line.executable:
                continue
            executable_lines += 1
            if line.covered:
                covered_lines += 1
            else:
                missed_locations.append(f"{changed_path}:{line_number}")
            total_branches += line.missed_branches + line.covered_branches
            covered_branches += line.covered_branches

    output = [
        f"new-code line: {percent(covered_lines, executable_lines)} "
        f"({covered_lines}/{executable_lines})",
        f"new-code branch: {percent(covered_branches, total_branches)} "
        f"({covered_branches}/{total_branches})",
    ]
    if missed_locations:
        output.append("uncovered: " + ", ".join(missed_locations))

    errors: List[str] = []
    if executable_lines and covered_lines * 100 < executable_lines * args.line_threshold:
        errors.append(
            f"line coverage {percent(covered_lines, executable_lines)} is below "
            f"{args.line_threshold}%"
        )
    if total_branches and covered_branches * 100 < total_branches * args.branch_threshold:
        errors.append(
            f"branch coverage {percent(covered_branches, total_branches)} is below "
            f"{args.branch_threshold}%"
        )
    return output, errors


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        output, errors = check(args)
    except (OSError, RuntimeError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for line in output:
        print(line)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
