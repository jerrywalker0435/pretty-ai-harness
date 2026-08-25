#!/usr/bin/env python3
"""Run isolated synthetic Plan-to-Execution forward replays with real Codex agents."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = Path(__file__).with_name("scenarios.json")
ORACLES_PATH = Path(__file__).with_name("oracles")
SKILLS = ("pretty-common", "pretty-writing-plan", "pretty-executing-plan")
DEFAULT_COMMAND_TIMEOUT = 900.0
ORACLE_SOURCES = {
    path.stem: path.read_text(encoding="utf-8")
    for path in sorted(ORACLES_PATH.glob("*.java"))
}

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>benchmark</groupId>
  <artifactId>quality-forward</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.source>1.8</maven.compiler.source>
    <maven.compiler.target>1.8</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.8.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>2.22.2</version>
      </plugin>
      <plugin>
        <groupId>org.jacoco</groupId>
        <artifactId>jacoco-maven-plugin</artifactId>
        <version>0.8.12</version>
      </plugin>
    </plugins>
  </build>
</project>
"""

SERVICE = """package benchmark;

public final class PolicyService {
    public String classify(int score) {
        return score >= 0 ? "STANDARD" : "INVALID";
    }
}
"""

TEST = """package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class PolicyServiceTest {
    @Test
    public void classifiesNonNegativeScore() {
        assertEquals("STANDARD", new PolicyService().classify(0));
    }

    @Test
    public void classifiesNegativeScore() {
        assertEquals("INVALID", new PolicyService().classify(-1));
    }
}
"""


@dataclass(frozen=True)
class ReplayResult:
    scenario: str
    repetition: int
    workspace: str
    plan_agent_exit: int
    plan_gate_exit: int
    execution_agent_exit: int
    execution_gate_exit: int
    oracle_exit: int
    infrastructure_error: str | None
    semantic_errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.infrastructure_error is None and not self.semantic_errors and all(
            code == 0
            for code in (
                self.plan_agent_exit,
                self.plan_gate_exit,
                self.execution_agent_exit,
                self.execution_gate_exit,
                self.oracle_exit,
            )
        )


@dataclass(frozen=True)
class ReplayEnvironment:
    repo: Path
    evidence: Path
    topic: str
    timeout: float


@dataclass(frozen=True)
class AgentGateResult:
    agent_exit: int
    gate_exit: int
    infrastructure_error: str | None


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(
    command: Sequence[str],
    cwd: Path,
    log: Path,
    *,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
) -> int:
    with log.open("w", encoding="utf-8") as output:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            output.write(f"\nevaluator command timed out after {timeout:.2f}s\n")
            return 124
        except FileNotFoundError:
            output.write(f"\nevaluator command failed to start: {command[0]} not found\n")
            return 127
        except OSError as error:
            output.write(
                f"\nevaluator command failed to start: {type(error).__name__}\n"
            )
            return 126
    return completed.returncode


def _git(
    repo: Path,
    *arguments: str,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
) -> None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("git command timed out") from error
    except OSError as error:
        raise RuntimeError(f"git failed to start: {type(error).__name__}") from error
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "git failed")


def _prepare_repo(
    workspace: Path,
    scenario: Mapping[str, object],
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
) -> tuple[Path, Path]:
    repo = workspace / "repo"
    evidence = workspace / "evidence"
    repo.mkdir(parents=True)
    evidence.mkdir()
    _write(repo / "pom.xml", POM)
    _write(repo / "src/main/java/benchmark/PolicyService.java", SERVICE)
    _write(repo / "src/test/java/benchmark/PolicyServiceTest.java", TEST)
    topic = str(scenario["id"])
    _write(repo / f"docs/pretty/{topic}/prd.md", f"# PRD\n\n{scenario['requirement']}\n")
    _write(repo / f"docs/pretty/{topic}/design.md", f"# Design\n\n{scenario['design']}\n")
    _write(repo / "Context.md", f"# Context\n\n{scenario['context']}\n")
    _write(repo / "Context-Map.md", f"# Context Map\n\n{scenario['context_map']}\n")
    for skill in SKILLS:
        shutil.copytree(ROOT / "skills" / skill, repo / ".agents/skills" / skill)
    _git(repo, "init", "-q", timeout=timeout)
    _git(repo, "config", "user.name", "Pretty Benchmark", timeout=timeout)
    _git(repo, "config", "user.email", "benchmark@example.invalid", timeout=timeout)
    _git(repo, "add", ".", timeout=timeout)
    _git(repo, "commit", "-q", "-m", "synthetic baseline", timeout=timeout)
    return repo, evidence


def _codex_command(repo: Path, evidence: Path, prompt: str) -> list[str]:
    return [
        "codex",
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(repo),
        "--add-dir",
        str(evidence),
        prompt,
    ]


def _plan_prompt(topic: str, evidence: Path) -> str:
    return f"""This is a synthetic forward evaluation with explicit approval to create the Plan.
Read and obey .agents/skills/pretty-writing-plan/SKILL.md and every resource it directly requires.
The primary input is docs/pretty/{topic}/design.md; the PRD and Design are approved in this prompt.
Read Context.md, Context-Map.md, pom.xml, and the real Java source and tests.
Create only docs/pretty/{topic}/plan.md. Spawn an independent reviewer agent; do not fabricate its review.
Write its structured evidence to {evidence / 'plan-review.json'} and make the Plan pass validate_plan.py with that evidence.
Do not implement production code, commit, or ask questions. Finish only after the Plan Gate passes.
"""


def _execution_prompt(topic: str, evidence: Path) -> str:
    return f"""This is the Execution half of a synthetic forward evaluation. The evaluator explicitly approves the current Plan.
Read and obey .agents/skills/pretty-executing-plan/SKILL.md and every resource it directly requires.
Implement docs/pretty/{topic}/plan.md in the real Java repository with tests. Use an actual independent reviewer agent.
Use {evidence} for all temporary evidence. Required final files are quality.json, coverage.json, build.json there and docs/pretty/{topic}/execution.md in the repo.
Run the supplied quality, coverage, and Execution validators. The coverage build must run tests and create a fresh JaCoCo report.
Do not commit, push, change approved upstream files, or ask questions. Finish only after the Execution Gate passes.
"""


def _semantic_errors(repo: Path, scenario: Mapping[str, object]) -> tuple[str, ...]:
    topic = str(scenario["id"])
    plan_path = repo / f"docs/pretty/{topic}/plan.md"
    execution_path = repo / f"docs/pretty/{topic}/execution.md"
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((repo / "src/main/java").rglob("*.java"))
    )
    errors = []
    plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    execution = execution_path.read_text(encoding="utf-8") if execution_path.is_file() else ""
    for token in scenario["plan_tokens"]:
        if str(token) not in plan:
            errors.append(f"Plan missing required contract token: {token}")
    for token in scenario["code_tokens"]:
        if str(token) not in production:
            errors.append(f"production code missing required token: {token}")
    if "- 状态：完成" not in execution:
        errors.append("Execution did not reach 完成")
    if "- 测试覆盖率：增量行覆盖率 " not in execution:
        errors.append("Execution conclusion lacks exact line coverage")
    if "，分支覆盖率 " not in execution and "，分支覆盖率不适用" not in execution:
        errors.append("Execution conclusion lacks exact branch coverage")
    return tuple(errors)


def _infrastructure_error(log: Path) -> str | None:
    if not log.is_file():
        return None
    content = log.read_text(encoding="utf-8").lower()
    markers = {
        "workspace is out of credits": "Codex workspace credits exhausted",
        "failed to initialize in-process app-server client": "Codex app-server initialization failed",
        "token_revoked": "Codex authentication expired",
        "refresh_token_invalidated": "Codex authentication expired",
        "please log out and sign in again": "Codex authentication expired",
        "evaluator command timed out": "Command timed out",
        "evaluator command failed to start": "Command failed to start",
    }
    return next((message for marker, message in markers.items() if marker in content), None)


def _validate_plan(environment: ReplayEnvironment, log: Path) -> int:
    return _run(
        [
            sys.executable,
            ".agents/skills/pretty-writing-plan/scripts/validate_plan.py",
            f"docs/pretty/{environment.topic}/plan.md",
            "--review-evidence",
            str(environment.evidence / "plan-review.json"),
        ],
        environment.repo,
        log,
        timeout=environment.timeout,
    )


def _validate_execution(environment: ReplayEnvironment, log: Path) -> int:
    return _run(
        [
            sys.executable,
            ".agents/skills/pretty-executing-plan/scripts/validate_execution.py",
            f"docs/pretty/{environment.topic}/execution.md",
            "--plan",
            f"docs/pretty/{environment.topic}/plan.md",
            "--quality-evidence",
            str(environment.evidence / "quality.json"),
            "--coverage-evidence",
            str(environment.evidence / "coverage.json"),
            "--build-evidence",
            str(environment.evidence / "build.json"),
        ],
        environment.repo,
        log,
        timeout=environment.timeout,
    )


def _run_behavior_oracle(
    environment: ReplayEnvironment,
    scenario: Mapping[str, object],
    log: Path,
) -> int:
    topic = str(scenario["id"])
    source = ORACLE_SOURCES.get(topic)
    if source is None:
        log.write_text(f"missing evaluator oracle for {topic}\n", encoding="utf-8")
        return 2
    _write(
        environment.repo / "src/test/java/benchmark/EvaluatorAcceptanceTest.java",
        source,
    )
    return _run(
        [
            "mvn",
            "-q",
            "-DskipTests=false",
            "-Dmaven.test.skip=false",
            "-Dmaven.test.failure.ignore=false",
            "-DfailIfNoTests=true",
            "-Dtest=EvaluatorAcceptanceTest",
            "test",
        ],
        environment.repo,
        log,
        timeout=environment.timeout,
    )


def _run_plan_stage(
    environment: ReplayEnvironment,
    workspace: Path,
) -> AgentGateResult:
    agent_log = workspace / "plan-agent.log"
    agent_exit = _run(
        _codex_command(
            environment.repo,
            environment.evidence,
            _plan_prompt(environment.topic, environment.evidence),
        ),
        environment.repo,
        agent_log,
        timeout=environment.timeout,
    )
    infrastructure_error = _infrastructure_error(agent_log)
    if agent_exit != 0:
        return AgentGateResult(agent_exit, -1, infrastructure_error)
    gate_log = workspace / "plan-gate.log"
    gate_exit = _validate_plan(environment, gate_log)
    return AgentGateResult(
        agent_exit,
        gate_exit,
        infrastructure_error or _infrastructure_error(gate_log),
    )


def _run_execution_stage(
    environment: ReplayEnvironment,
    workspace: Path,
) -> AgentGateResult:
    agent_log = workspace / "execution-agent.log"
    agent_exit = _run(
        _codex_command(
            environment.repo,
            environment.evidence,
            _execution_prompt(environment.topic, environment.evidence),
        ),
        environment.repo,
        agent_log,
        timeout=environment.timeout,
    )
    infrastructure_error = _infrastructure_error(agent_log)
    if agent_exit != 0:
        return AgentGateResult(agent_exit, -1, infrastructure_error)
    gate_log = workspace / "execution-gate.log"
    gate_exit = _validate_execution(environment, gate_log)
    return AgentGateResult(
        agent_exit,
        gate_exit,
        infrastructure_error or _infrastructure_error(gate_log),
    )


def run_one(
    output_root: Path,
    scenario: Mapping[str, object],
    repetition: int,
    timeout: float,
) -> ReplayResult:
    topic = str(scenario["id"])
    workspace = output_root / f"{topic}-{repetition}"
    repo, evidence = _prepare_repo(workspace, scenario, timeout)
    environment = ReplayEnvironment(repo, evidence, topic, timeout)
    plan_stage = _run_plan_stage(environment, workspace)
    execution_stage = AgentGateResult(-1, -1, None)
    if plan_stage.agent_exit == 0 and plan_stage.gate_exit == 0:
        execution_stage = _run_execution_stage(environment, workspace)
    infrastructure_error = (
        plan_stage.infrastructure_error or execution_stage.infrastructure_error
    )
    oracle_exit = -1
    if execution_stage.agent_exit == 0 and execution_stage.gate_exit == 0:
        oracle_log = workspace / "behavior-oracle.log"
        oracle_exit = _run_behavior_oracle(environment, scenario, oracle_log)
        infrastructure_error = infrastructure_error or _infrastructure_error(oracle_log)
    semantic_errors = [] if infrastructure_error else list(_semantic_errors(repo, scenario))
    if not infrastructure_error and oracle_exit > 0:
        semantic_errors.append("evaluator-owned behavior oracle failed")
    return ReplayResult(
        topic,
        repetition,
        str(workspace),
        plan_stage.agent_exit,
        plan_stage.gate_exit,
        execution_stage.agent_exit,
        execution_stage.gate_exit,
        oracle_exit,
        infrastructure_error,
        tuple(semantic_errors),
    )


def _run_job(job: tuple[Path, Mapping[str, object], int, float]) -> ReplayResult:
    output_root, scenario, repetition, timeout = job
    try:
        return run_one(output_root, scenario, repetition, timeout)
    # Preserve completed scenario results when one isolated worker fails unexpectedly.
    except Exception as error:
        topic = str(scenario["id"])
        workspace = output_root / f"{topic}-{repetition}"
        workspace.mkdir(parents=True, exist_ok=True)
        message = f"Benchmark worker failed: {type(error).__name__}"
        _write(
            workspace / "infrastructure-error.log",
            f"{message}: {error}\n",
        )
        return ReplayResult(
            topic,
            repetition,
            str(workspace),
            -1,
            -1,
            -1,
            -1,
            -1,
            message,
            (),
        )


def _load_scenarios(selected: set[str]) -> list[dict[str, object]]:
    payload = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    scenarios = [scenario for scenario in payload if not selected or scenario["id"] in selected]
    unknown = selected - {str(scenario["id"]) for scenario in scenarios}
    if unknown:
        raise ValueError(f"unknown scenarios: {', '.join(sorted(unknown))}")
    return scenarios


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--command-timeout",
        type=float,
        default=DEFAULT_COMMAND_TIMEOUT,
        help="每条 Agent、Gate 或 oracle 命令的超时秒数",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    if args.runs < 1:
        raise ValueError("--runs must be positive")
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    if args.command_timeout <= 0:
        raise ValueError("--command-timeout must be positive")
    output_root = args.output_root or Path(tempfile.mkdtemp(prefix="pretty-quality-forward-"))
    output_root.mkdir(parents=True, exist_ok=True)
    scenarios = _load_scenarios(set(args.scenario))
    jobs = [
        (output_root, scenario, repetition, args.command_timeout)
        for scenario in scenarios
        for repetition in range(1, args.runs + 1)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(
            executor.map(_run_job, jobs)
        )
    payload = {
        "kind": "synthetic_agent_forward_replay",
        "scenario_count": len(scenarios),
        "runs_per_scenario": args.runs,
        "passed": all(result.passed for result in results),
        "results": [result.__dict__ | {"passed": result.passed} for result in results],
    }
    _write(output_root / "summary.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
