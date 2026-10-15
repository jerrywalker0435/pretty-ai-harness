#!/usr/bin/env python3
"""Validate the deterministic structure of a Pretty Design."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_SECTIONS = (
    "设计结论",
    "方案全景",
    "关键设计与权衡",
    "设计边界",
    "实施影响",
    "验证与风险",
    "Executing交付",
)
FORBIDDEN_HEADINGS = ("覆盖需求", "需求覆盖", "实施计划", "Plan")
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待定|待确认|未决|待澄清",
    re.IGNORECASE,
)
MERMAID_BLOCK_PATTERN = re.compile(
    r"```mermaid\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL
)
MERMAID_START_PATTERN = re.compile(
    r"^(?:flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram)\b",
    re.IGNORECASE,
)
SQL_BLOCK_PATTERN = re.compile(
    r"^[ \t]*```sql[ \t]*\n(?P<body>.*?)^[ \t]*```[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
DDL_STATEMENT_PATTERN = re.compile(
    r"^\s*(?:CREATE\s+(?:(?:TEMPORARY|UNIQUE)\s+)?(?:TABLE|INDEX)|"
    r"ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX)|RENAME\s+TABLE)\s+\S",
    re.IGNORECASE | re.MULTILINE,
)
DDL_DELIVERY_PATTERN = re.compile(
    r"\bDDL\b(?![ \t：:]*(?:无|不适用)(?:$|[\s；;，,：:]))",
    re.IGNORECASE,
)
REQ_REF = re.compile(r"\bREQ-\d{3}\b")
AC_REF = re.compile(r"\bAC-\d{3}\b")
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
HANDOFF_TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})\s*$", re.MULTILINE)
TASK_DELIVERY_FIELDS = ("Execution 交付", "人工运维产物")
HANDOFF_REQUIRED_FIELDS = ("公共验证入口", "影响锚点", *TASK_DELIVERY_FIELDS)
HANDOFF_FIELDS = (*HANDOFF_REQUIRED_FIELDS, "依赖")
EXTERNAL_VALIDATION_PATTERN = re.compile(
    r"集成测试|integration\s+tests?|Testcontainers|端到端测试|\bE2E\b|"
    r"真实(?:数据库|事务)|(?:SQL\s*)?执行计划|联调",
    re.IGNORECASE,
)
VALIDATION_REQUIREMENT_PATTERN = re.compile(
    r"需要|必须|应当|执行阶段|验收|前置条件|完成条件|门禁|"
    r"公共验证入口|Execution\s*交付|依赖",
    re.IGNORECASE,
)
PATH_SYMBOL_PATTERN = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.$-]+\.[A-Za-z0-9_-]+#"
    r"[A-Za-z_$][A-Za-z0-9_.$]*(?:\([^\n)]*\))?"
)
REPOSITORY_FILE_PATTERN = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.$-]+\."
    r"(?:java|xml|gradle|kts|sql|yaml|yml|properties|json)(?=$|[\s`；;,])",
    re.IGNORECASE,
)
CONFIG_ARTIFACT_PATTERN = re.compile(
    r"配置(?:数据|表)?\s*(?:DML|SQL|脚本|迁移)|配置(?:激活|禁用|回滚)|"
    r"事件定义|模板关系|白名单|种子数据|reference\s+data|seed\s+data",
    re.IGNORECASE,
)
CONFIG_CHANGE_PATTERN = re.compile(
    r"配置(?:数据|表)?\s*(?:DML|SQL|脚本|迁移)|"
    r"(?:INSERT|UPDATE|DELETE|MERGE|UPSERT|REPLACE\s+INTO)[^\n]{0,80}"
    r"(?:config|define|relation|配置|事件|模板)|"
    r"(?:事件定义|模板关系|白名单|种子数据|reference\s+data|seed\s+data)"
    r"[^\n。；;]{0,28}(?:新增|写入|更新|失效|激活|禁用|回滚|删除|DML|SQL|脚本|迁移)|"
    r"(?:新增|写入|更新|失效|激活|禁用|回滚|删除)[^\n。；;]{0,28}"
    r"(?:事件定义|模板关系|白名单|种子数据|reference\s+data|seed\s+data)",
    re.IGNORECASE,
)
STRUCTURAL_DDL_PATTERN = re.compile(
    r"\b(?:DDL|ALTER\s+TABLE|CREATE\s+(?:TABLE|INDEX)|DROP\s+(?:TABLE|INDEX))\b|"
    r"表(?:结构)?|字段|索引",
    re.IGNORECASE,
)
EXECUTION_CONFIG_ASSIGNMENT = re.compile(
    r"(?:Execution[^\n。；;]{0,36}(?:生成|创建|修改|交付|执行|运行|应用|部署|迁移)"
    r"[^\n。；;]{0,48}(?:配置(?:数据|表)?\s*DML|事件定义|模板关系|白名单|种子数据|"
    r"reference\s+data|seed\s+data|激活|禁用|回滚)"
    r"|(?:配置(?:数据|表)?\s*DML|事件定义|模板关系|白名单|种子数据|reference\s+data|"
    r"seed\s+data|激活|禁用|回滚)[^\n。；;]{0,24}由\s*Execution[^\n。；;]{0,20}"
    r"(?:生成|创建|修改|交付|执行|运行|应用|部署|迁移))",
    re.IGNORECASE,
)
EXECUTION_DDL_ACTION = re.compile(
    r"(?:Execution[^\n。；;]{0,36}(?:执行|运行|应用|部署|迁移)[^\n。；;]{0,48}"
    r"(?:DDL|ALTER\s+TABLE|CREATE\s+(?:TABLE|INDEX)|DROP\s+(?:TABLE|INDEX)|表|字段|索引)|"
    r"(?:DDL|ALTER\s+TABLE|CREATE\s+(?:TABLE|INDEX)|DROP\s+(?:TABLE|INDEX)|表|字段|索引)"
    r"[^\n。；;]{0,24}由\s*Execution[^\n。；;]{0,20}(?:执行|运行|应用|部署|迁移))",
    re.IGNORECASE,
)
LOW_QUALITY_DIRECTIVE = re.compile(
    r"(?:使用|采用|新增|允许|保留)[^\n。；;]{0,28}\bcontinue\b|"
    r"(?:返回|使用|允许)[^\n。；;]{0,20}(?:null|空指针)|"
    r"(?:必填|必需|required)[^\n。；;]{0,48}(?:缺失|为空|null)[^\n。；;]{0,32}"
    r"(?:返回空|emptyList|emptySet|emptyMap|Optional\.empty)|"
    r"(?:添加|新增|保留|要求)[^\n。；;]{0,24}(?:中文步骤注释|普通\s*JavaDoc|步骤注释)",
    re.IGNORECASE,
)
QUALITY_EXCEPTION_BASIS = re.compile(
    r"(?:外部|遗留|框架|兼容)[^\n]{0,80}(?:#|Schema|签名|测试)",
    re.IGNORECASE,
)
GENERIC_NORMALIZATION_DIRECTIVE = re.compile(
    r"(?:使用|采用|新增|允许|保留|复用|调用)[^\n。；;]{0,32}"
    r"(?:normalize(?:Text|String|Value|Input)?|normalise(?:Text|String|Value|Input)?|"
    r"clean(?:Text|String|Value|Input)?|trim(?:Text|String|Value|Input|ToNull)?|"
    r"通用[^\n。；;]{0,12}(?:规范化|归一化)[^\n。；;]{0,12}(?:Helper|helper|工具方法))",
    re.IGNORECASE,
)


def section_headings(document: str) -> list[str]:
    """Return level-two headings in document order."""
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def validate_mermaid_blocks(document: str) -> list[str]:
    """Return errors for empty or unsupported Mermaid blocks."""
    errors: list[str] = []
    for block in MERMAID_BLOCK_PATTERN.finditer(document):
        lines = [line.strip() for line in block.group("body").splitlines() if line.strip()]
        if not lines:
            errors.append("Mermaid 图块不能为空")
        elif not MERMAID_START_PATTERN.match(lines[0]):
            errors.append("Mermaid 图块必须声明 flowchart、sequenceDiagram、stateDiagram、classDiagram 或 erDiagram")
    return errors


def _field_value(document: str, field: str) -> str | None:
    lines = document.splitlines()
    marker = re.compile(rf"^-\s*{re.escape(field)}：\s*(.*)$")
    for index, line in enumerate(lines):
        match = marker.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if value:
            return value

        # Handoff fields may use a fenced block so that every entry is
        # readable on its own line. Read only until the next task field.
        entries: list[str] = []
        in_fence = False
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            is_next_field = stripped.startswith("- ") or stripped.startswith("### ") or stripped.startswith("## ")
            if not in_fence and is_next_field:
                break
            if stripped:
                entries.append(stripped)
        return "\n".join(entries) or None
    return None


def _ddl_code_errors(document: str) -> list[str]:
    panorama = section_body(document, "方案全景")
    ddl_heading = re.search(r"^####\s+表结构变更 DDL(?:[（(].*)?\s*$", panorama, re.MULTILINE)
    has_ddl_delivery = any(
        DDL_DELIVERY_PATTERN.search(_field_value(body, "Execution 交付") or "")
        for _, body in _task_blocks(section_body(document, "Executing交付"), HANDOFF_TASK_HEADING)
    )
    if not ddl_heading and not has_ddl_delivery:
        return []
    for block in SQL_BLOCK_PATTERN.finditer(panorama):
        sql = re.sub(r"/\*.*?\*/|--[^\n]*", "", block.group("body"), flags=re.DOTALL)
        if DDL_STATEMENT_PATTERN.search(sql):
            return []
    return ["声明表结构变更 DDL 或 DDL 交付时，方案全景必须直接包含提供 DDL 语句的 sql 代码块"]


def _has_positive_config_change(document: str) -> bool:
    return any(
        CONFIG_CHANGE_PATTERN.search(line)
        and not re.search(r"(?:不|不得|禁止|无|不属于|由人工运维|人工处理|不生成|不执行)", line)
        for line in document.splitlines()
    )


def _task_delivery_errors(task: str, body: str) -> list[str]:
    execution_delivery = _field_value(body, "Execution 交付") or ""
    operations_delivery = _field_value(body, "人工运维产物") or ""
    errors = []
    if CONFIG_ARTIFACT_PATTERN.search(execution_delivery):
        errors.append(f"{task} 不得把配置数据 DML 或配置运维动作列入 Execution 交付")
    if STRUCTURAL_DDL_PATTERN.search(execution_delivery) and re.search(
        r"执行|运行|应用|部署|迁移", execution_delivery
    ):
        errors.append(f"{task} 的 DDL 只能作为文件交付，不得列为 Execution 执行动作")
    if _has_positive_config_change(body) and not CONFIG_ARTIFACT_PATTERN.search(operations_delivery):
        errors.append(f"{task} 提及配置数据变更时必须声明人工运维产物")
    return errors


def _not_applicable(value: str) -> bool:
    normalized = value.strip().strip("`")
    return normalized == "无" or normalized.startswith(("不适用：", "不适用:"))


def _execution_handoff_errors(task: str, body: str) -> list[str]:
    public_entry = _field_value(body, "公共验证入口") or ""
    anchors = _field_value(body, "影响锚点") or ""
    delivery = _field_value(body, "Execution 交付") or ""
    errors: list[str] = []
    for field, value in (("公共验证入口", public_entry), ("影响锚点", anchors)):
        if _not_applicable(value):
            continue
        entries = [entry.strip(" `") for entry in value.splitlines() if entry.strip(" `")]
        if not entries:
            entries = [value.strip(" `")]
        if any(not re.search(r"(?:现有|新增)", entry) for entry in entries):
            errors.append(f"{task} 的{field}必须标记现有或新增")
        if any(not PATH_SYMBOL_PATTERN.search(entry) for entry in entries):
            errors.append(f"{task} 的{field}必须包含仓库相对路径#symbol")
    if not _not_applicable(delivery):
        if not re.search(r"(?:构建根|模块)", delivery):
            errors.append(f"{task} 的 Execution 交付必须声明构建根或模块")
        if not re.search(r"\b(?:Add|Modify|Test|DDL)\b", delivery):
            errors.append(f"{task} 的 Execution 交付必须标记 Add/Modify/Test/DDL")
        if not REPOSITORY_FILE_PATTERN.search(delivery):
            errors.append(f"{task} 的 Execution 交付必须包含仓库相对文件路径")
    return errors


def _has_manual_config_owner(handoff: str) -> bool:
    return any(
        CONFIG_ARTIFACT_PATTERN.search(_field_value(body, "人工运维产物") or "")
        for _, body in _task_blocks(handoff, HANDOFF_TASK_HEADING)
    )


def _delivery_assignment_errors(document: str) -> list[str]:
    errors = []
    for line in document.splitlines():
        if re.search(r"Execution[^\n]{0,12}(?:不|不得|禁止|无需)", line):
            continue
        if EXECUTION_CONFIG_ASSIGNMENT.search(line):
            errors.append("Execution 不得生成、交付或执行配置数据 DML")
        if EXECUTION_DDL_ACTION.search(line):
            errors.append("Execution 只能交付 DDL 文件，不得执行或间接执行 DDL")
    return sorted(set(errors))


def _external_validation_errors(document: str) -> list[str]:
    risk_lines = set(section_body(document, "验证与风险").splitlines())
    handoff_lines = set(section_body(document, "Executing交付").splitlines())
    errors = []
    for line in document.splitlines():
        if not EXTERNAL_VALIDATION_PATTERN.search(line):
            continue
        manual = line.startswith("- 人工外部验证：")
        if manual and line in risk_lines and "不作为 Plan/Execution 门禁" in line:
            continue
        if line in handoff_lines or manual or VALIDATION_REQUIREMENT_PATTERN.search(line):
            errors.append(
                "外部验证不得作为 Execution 交付或门禁；请在验证与风险使用独立的"
                "人工外部验证条目，并声明不作为 Plan/Execution 门禁"
            )
    return sorted(set(errors))


def _quality_directive_errors(document: str) -> list[str]:
    errors = []
    for line in document.splitlines():
        if re.search(
            r"(?:不|不得|禁止|避免|移除)[^\n]{0,24}(?:normalize|normalise|cleanText|trimText|"
            r"trimToNull|通用[^\n。；;]{0,12}(?:规范化|归一化)[^\n。；;]{0,12}(?:Helper|helper|工具方法))",
            line,
            re.IGNORECASE,
        ):
            continue
        if re.search(r"(?:不|不得|禁止|避免|移除)[^\n]{0,16}(?:continue|null|步骤注释|JavaDoc)", line, re.IGNORECASE):
            continue
        if GENERIC_NORMALIZATION_DIRECTIVE.search(line):
            errors.append("Design 不得要求通用文本规范化 Helper；规范化必须由有领域归属的首个信任边界完成")
            continue
        if LOW_QUALITY_DIRECTIVE.search(line) and not QUALITY_EXCEPTION_BASIS.search(line):
            errors.append("Design 不得用普通实现指令降级 Pretty 共享质量规则；合法外部或遗留例外必须绑定 Symbol 和可核查事实")
    return sorted(set(errors))


def _task_blocks(section: str, heading_pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(heading_pattern.finditer(section))
    task_blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        task_blocks.append((match.group(1), section[match.start():end]))
    return task_blocks


def _missing_fields(body: str, fields: Sequence[str]) -> list[str]:
    return [
        field
        for field in fields
        if _field_value(body, field) is None
    ]


def _impact_errors(impact: str) -> tuple[list[str], list[str]]:
    task_blocks = _task_blocks(impact, TASK_HEADING)
    tasks = [task for task, _ in task_blocks]
    errors: list[str] = []
    if not tasks:
        errors.append("实施影响至少需要一个 TASK")
    if [int(task.split("-")[1]) for task in tasks] != list(range(1, len(tasks) + 1)):
        errors.append("TASK 编号必须从 TASK-001 连续递增")
    if not re.search(r"^###\s+变更职责链路\s*$", impact, re.MULTILINE):
        errors.append("实施影响需要供人工评审的变更职责链路")
    if any(_field_value(impact, field) for field in HANDOFF_FIELDS):
        errors.append("实施影响不得包含 Executing交付字段")
    for task, body in task_blocks:
        missing = _missing_fields(body, ("结果", "输入与不变量", "失败语义", "验证观察面"))
        if missing:
            errors.append(f"{task} 缺少字段：{', '.join(missing)}")
        if not REQ_REF.search(body) or not AC_REF.search(body):
            errors.append(f"{task} 必须引用至少一个 REQ-* 和 AC-*")
    if len(set(tasks)) != len(tasks):
        errors.append("TASK ID 必须唯一")
    return tasks, errors


def _handoff_errors(document: str, handoff: str, impact_tasks: list[str]) -> list[str]:
    task_blocks = _task_blocks(handoff, HANDOFF_TASK_HEADING)
    handoff_tasks = [task for task, _ in task_blocks]
    errors: list[str] = []
    if re.search(r"^###\s+变更职责链路\s*$", handoff, re.MULTILINE):
        errors.append("变更职责链路应位于实施影响，不得放入 Executing交付")
    if handoff_tasks != impact_tasks:
        errors.append("Executing交付的 TASK ID 必须与实施影响一致且顺序相同")
    if _has_positive_config_change(document) and not _has_manual_config_owner(handoff):
        errors.append("Design 提及配置数据变更时必须由 Executing TASK 声明人工运维产物")
    for task, body in task_blocks:
        missing = _missing_fields(body, HANDOFF_REQUIRED_FIELDS)
        if missing:
            errors.append(f"Executing {task} 缺少字段：{', '.join(missing)}")
        errors.extend(_task_delivery_errors(task, body))
        errors.extend(_execution_handoff_errors(task, body))
    return errors


def validate_design_document(document: str) -> list[str]:
    """Return deterministic structural errors for a final Design."""
    headings = section_headings(document)
    errors: list[str] = []
    if headings != list(REQUIRED_SECTIONS):
        errors.append(f"Design 二级章节必须依次为：{', '.join(REQUIRED_SECTIONS)}")
    errors.extend(f"禁止章节：{heading}" for heading in FORBIDDEN_HEADINGS if heading in headings)
    if PLACEHOLDER_PATTERN.search(document):
        errors.append("Design 仍包含占位内容或未决项")
    errors.extend(validate_mermaid_blocks(document))
    errors.extend(_ddl_code_errors(document))
    errors.extend(_delivery_assignment_errors(document))
    errors.extend(_external_validation_errors(document))
    errors.extend(_quality_directive_errors(document))
    impact = section_body(document, "实施影响")
    impact_tasks, impact_errors = _impact_errors(impact)
    errors.extend(impact_errors)
    handoff = section_body(document, "Executing交付")
    errors.extend(_handoff_errors(document, handoff, impact_tasks))
    return errors


def _contract_ids(prd: str, prefix: str) -> set[str]:
    return set(re.findall(rf"^###\s+({prefix}-\d{{3}})[：:]", prd, re.MULTILINE))


def _contract_coverage_errors(design: str, prd: str) -> list[str]:
    impact = section_body(design, "实施影响")
    errors = []
    for prefix in ("REQ", "AC"):
        defined = _contract_ids(prd, prefix)
        referenced = set(re.findall(rf"\b{prefix}-\d{{3}}\b", impact))
        for identifier in sorted(referenced - defined):
            errors.append(f"实施影响引用了不存在的 {identifier}")
        for identifier in sorted(defined - referenced):
            errors.append(f"实施影响未覆盖 {identifier}")
    return errors


def validate_design(design_path: Path) -> list[str]:
    try:
        design = design_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"读取 Design 失败：{error}"]
    prd_path = design_path.with_name("prd.md")
    try:
        prd = prd_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"Design 需要同目录 prd.md：{error}"]
    errors = validate_design_document(design)
    errors.extend(_contract_coverage_errors(design, prd))
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path, help="Design 文件路径")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        errors = validate_design(args.design)
    except (OSError, ValueError) as error:
        print(f"Design 校验失败：{error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print("Design 结构校验：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
