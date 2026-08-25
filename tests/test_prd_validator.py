from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-writing-prd/scripts"))

from validate_prd import validate_prd_document  # noqa: E402

VALID_PRD = """# Example PRD
## 背景与问题
背景。
## 目标与非目标
目标。
## 用户与场景
场景。
## 需求
### REQ-001：返回订单
返回订单。
## 验收标准
### AC-001：订单可见
- Given 存在订单，When 查询，Then 返回订单。
"""


class PrdValidatorTest(unittest.TestCase):
    def test_accepts_stable_requirement_and_acceptance_ids(self) -> None:
        self.assertEqual([], validate_prd_document(VALID_PRD))

    def test_requires_continuous_ids(self) -> None:
        errors = validate_prd_document(VALID_PRD.replace("REQ-001", "REQ-002"))
        self.assertIn("REQ-* 编号必须从 001 连续递增", errors)


if __name__ == "__main__":
    unittest.main()
