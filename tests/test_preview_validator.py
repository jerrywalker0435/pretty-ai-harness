from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from validate_preview import validate_preview  # noqa: E402

PREVIEW = """# example Execution Preview

> 本文档是当前 Design 和仓库事实下的非权威实施预演；Apply 不强制依赖本文档。

## 受影响链路
入口到服务。

## TASK 提案
### TASK-001：返回订单
- 覆盖：TASK-001、REQ-001、AC-001
**Files:**
- Modify: `app/src/main/java/example/OrderService.java`
- Symbol: `app/src/main/java/example/OrderService.java#OrderService#load`
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


class PreviewValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.topic = Path(self.temporary.name) / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        (self.topic / "prd.md").write_text("# PRD\n", encoding="utf-8")
        (self.topic / "design.md").write_text("### TASK-001：返回订单\n", encoding="utf-8")
        production = Path(self.temporary.name) / "app/src/main/java/example/OrderService.java"
        test = Path(self.temporary.name) / "app/src/test/java/example/OrderServiceTest.java"
        production.parent.mkdir(parents=True)
        test.parent.mkdir(parents=True)
        production.write_text("class OrderService {}\n", encoding="utf-8")
        test.write_text("class OrderServiceTest {}\n", encoding="utf-8")
        self.preview = self.topic / "execution-preview.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_complete_preview_without_independent_review(self) -> None:
        self.preview.write_text(PREVIEW, encoding="utf-8")
        errors, findings = validate_preview(self.preview)
        self.assertEqual([], errors)
        self.assertEqual([], findings)

    def test_rejects_disabled_test_proposal(self) -> None:
        self.preview.write_text(PREVIEW.replace("@Test", "@Disabled\n@Test"), encoding="utf-8")
        errors, _ = validate_preview(self.preview)
        self.assertTrue(any(error.startswith("DISABLED-TEST") for error in errors))

    def test_rejects_fully_qualified_disabled_test_proposal(self) -> None:
        self.preview.write_text(
            PREVIEW.replace("@Test", "@org.junit.jupiter.api.Disabled\n@Test"),
            encoding="utf-8",
        )
        errors, _ = validate_preview(self.preview)
        self.assertTrue(any(error.startswith("DISABLED-TEST") for error in errors))

    def test_modify_path_must_exist_in_repository(self) -> None:
        self.preview.write_text(
            PREVIEW.replace("OrderService.java", "MissingService.java"),
            encoding="utf-8",
        )
        errors, _ = validate_preview(self.preview)
        self.assertTrue(any("Modify path does not exist" in error for error in errors))

    def test_symbol_type_must_exist_or_be_declared_in_proposal(self) -> None:
        self.preview.write_text(
            PREVIEW.replace("#OrderService#load", "#MissingService#load"),
            encoding="utf-8",
        )
        errors, _ = validate_preview(self.preview)
        self.assertTrue(any("Symbol type is absent" in error for error in errors))

    def test_requires_design_task_set(self) -> None:
        self.preview.write_text(PREVIEW.replace("TASK-001", "TASK-002"), encoding="utf-8")
        errors, _ = validate_preview(self.preview)
        self.assertTrue(any("TASK set must match Design" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
