from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from execution_contract import contract_preflight_errors  # noqa: E402


DESIGN = """# Design
## 实施影响
### TASK-001：返回订单
- 结果：返回订单。
- 输入与不变量：订单编号必填。
- 失败语义：非法输入、合法缺失和依赖故障可区分。
- 公共验证入口：OrderService#load
- 影响锚点：OrderService
- 验证观察面：返回值或异常。
- Execution 交付：Java、测试
- 人工运维产物：无
"""


def matrix() -> dict[str, object]:
    return {
        "contract_preflight": {
            area: {"status": "clear", "evidence": [f"design.md#{area}"]}
            for area in (
                "module_boundaries",
                "runtime_semantics",
                "verification_surface",
                "delivery_ownership",
            )
        },
        "tasks": [{"id": "TASK-001"}],
    }


class ExecutionContractTest(unittest.TestCase):
    def test_accepts_complete_writer_preflight(self) -> None:
        self.assertEqual([], contract_preflight_errors(DESIGN, matrix()))

    def test_rejects_missing_runtime_semantics_evidence(self) -> None:
        candidate = matrix()
        candidate["contract_preflight"]["runtime_semantics"]["evidence"] = []
        self.assertIn(
            "contract_preflight runtime_semantics needs concrete evidence",
            contract_preflight_errors(DESIGN, candidate),
        )

    def test_rejects_unresolved_design_contract(self) -> None:
        self.assertIn(
            "Design contains unresolved contract language",
            contract_preflight_errors(DESIGN.replace("返回订单。", "返回订单，事务待定。"), matrix()),
        )

    def test_not_applicable_requires_reason(self) -> None:
        candidate = matrix()
        candidate["contract_preflight"]["delivery_ownership"] = {
            "status": "not_applicable",
            "evidence": ["Design has no operational artifact"],
        }
        self.assertIn(
            "contract_preflight delivery_ownership not_applicable needs a reason",
            contract_preflight_errors(DESIGN, candidate),
        )

    def test_rejects_design_without_executable_task(self) -> None:
        candidate = matrix()
        candidate["tasks"] = []
        self.assertIn(
            "Design needs at least one executable TASK",
            contract_preflight_errors("# Design\n", candidate),
        )


if __name__ == "__main__":
    unittest.main()
