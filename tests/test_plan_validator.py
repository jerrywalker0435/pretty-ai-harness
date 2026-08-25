from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-writing-plan/scripts"))

from validate_plan import plan_candidate_hash, validate_plan  # noqa: E402


VALID_PLAN = """# example Implementation Plan

## 变更链路

入口到服务。

## 实施任务

### TASK-001：返回订单

约束：
- 查询缺失抛出领域异常。

**Files:**
- Modify: `app/src/main/java/example/OrderService.java`
- Test: `app/src/test/java/example/OrderServiceTest.java`

修改：

```java
public Order load(OrderId id) {
    return repository.require(id);
}
```

测试：

```java
@Test
void returnsOrder() {
    assertThat(service.load(id)).isEqualTo(expected);
}
```
"""

VALID_SQL_PLAN = """# event-index Implementation Plan

## 实施任务

### TASK-001：创建事件查询索引

**Files:**
- Modify: `db/migration/V2__event_index.sql`

修改：

```sql
CREATE INDEX idx_event_code ON service_event (event_define_code);
```

数据库验证：

- 类型：INDEX
- 目标引擎：MySQL 8.0
- 期望：索引存在且事件编码查询使用 idx_event_code

```sql
SHOW INDEX FROM service_event WHERE Key_name = 'idx_event_code';
```
"""


def review_for(plan: str) -> dict[str, object]:
    return {
        "candidate_sha256": plan_candidate_hash(plan),
        "reviewer": "reviewer-1",
        "independent": True,
        "risks": [
            {"id": "JAVA_OOD", "owner": "121-java-object-oriented-design", "evidence": ["OrderService#load"]}
        ],
        "accepted_findings": [],
        "blocking_findings": [],
    }


class PlanValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.topic = Path(self.temporary.name) / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        (self.topic / "design.md").write_text("# Design\n", encoding="utf-8")
        (self.topic / "prd.md").write_text("# PRD\n", encoding="utf-8")
        self.plan = self.topic / "plan.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_complete_plan_with_independent_review(self) -> None:
        self.plan.write_text(VALID_PLAN, encoding="utf-8")

        errors, findings = validate_plan(
            self.plan,
            review_for(VALID_PLAN),
            require_review=True,
        )

        self.assertEqual([], errors)
        self.assertEqual([], findings)

    def test_requires_design_and_prd_siblings(self) -> None:
        self.plan.write_text(VALID_PLAN, encoding="utf-8")
        (self.topic / "design.md").unlink()
        (self.topic / "prd.md").unlink()

        errors, _ = validate_plan(self.plan)

        self.assertIn("Plan requires sibling design.md", errors)
        self.assertIn("Plan requires sibling prd.md", errors)

    def test_logic_change_requires_a_java_test_proposal(self) -> None:
        plan = VALID_PLAN.replace("```java\n@Test\nvoid returnsOrder()", "```text\nreturns order")
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn("TASK-001 测试 must contain a non-empty Java code block", errors)

    def test_production_error_cannot_be_accepted(self) -> None:
        plan = VALID_PLAN.replace("return repository.require(id);", "return null;")
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan, review_for(plan), require_review=True)

        self.assertTrue(any(error.startswith("NULL-RETURN at") for error in errors))

    def test_missing_implementation_section_returns_an_error(self) -> None:
        plan = "# example Implementation Plan\n\n## 变更链路\n\n入口到服务。\n"
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn("Plan must contain exactly one '实施任务' section", errors)

    def test_rejects_empty_modification_block(self) -> None:
        plan = VALID_PLAN.replace(
            "```java\npublic Order load(OrderId id) {\n    return repository.require(id);\n}\n```",
            "```text\n\n```",
        )
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn("TASK-001 修改 must contain a non-empty code or content block", errors)

    def test_rejects_empty_java_test_block(self) -> None:
        plan = VALID_PLAN.replace(
            "```java\n@Test\nvoid returnsOrder() {\n    assertThat(service.load(id)).isEqualTo(expected);\n}\n```",
            "```java\n\n```",
        )
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn("TASK-001 测试 must contain a non-empty Java code block", errors)

    def test_sql_change_uses_database_validation_without_java_unit_test(self) -> None:
        self.plan.write_text(VALID_SQL_PLAN, encoding="utf-8")

        errors, findings = validate_plan(self.plan)

        self.assertEqual([], errors)
        self.assertEqual([], findings)

    def test_sql_change_rejects_sql_block_under_test_section(self) -> None:
        plan = VALID_SQL_PLAN.replace(
            "数据库验证：",
            "测试：\n\n```sql\nSELECT COUNT(*) FROM service_event;\n```\n\n数据库验证：",
        )
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn("TASK-001 SQL verification belongs under 数据库验证, not 测试", errors)

    def test_sql_change_requires_database_validation_contract(self) -> None:
        plan = VALID_SQL_PLAN[: VALID_SQL_PLAN.index("\n数据库验证：")]
        self.plan.write_text(plan, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn(
            "TASK-001 SQL change must contain 数据库验证, not a Java unit test",
            errors,
        )

    def test_java_and_sql_change_requires_both_validation_types(self) -> None:
        mixed = VALID_PLAN.replace(
            "- Test: `app/src/test/java/example/OrderServiceTest.java`",
            "- Test: `app/src/test/java/example/OrderServiceTest.java`\n"
            "- Modify: `db/migration/V2__event_index.sql`",
        ).replace(
            "测试：",
            "```sql\nCREATE INDEX idx_event_code ON service_event (event_define_code);\n```\n\n测试：",
        )
        self.plan.write_text(mixed, encoding="utf-8")

        errors, _ = validate_plan(self.plan)

        self.assertIn(
            "TASK-001 SQL change must contain 数据库验证, not a Java unit test",
            errors,
        )
        self.assertNotIn("TASK-001 logic change must contain 测试", errors)


if __name__ == "__main__":
    unittest.main()
