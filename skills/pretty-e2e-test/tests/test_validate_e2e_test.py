from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_e2e_test import validate


VALID_REPORT = """# 端到端测试结果

## 场景总览

| 场景 | Review 状态 | 执行结果 |
|---|---|---|
| S01 创建 | 执行 | 通过 |

## 场景详情

### S01 创建

前置条件：环境可用

数据副作用：创建唯一数据

结果：HTTP 200

命令或脚本（本场景可单独执行；可直接包含 token、Cookie 等凭证）：

```bash
curl --max-time 10 -H 'Authorization: Bearer test-token' https://example.test/items
```

返回值 JSON：

```json
{
  "success": true,
  "code": 200,
  "msg": "success",
  "data": {}
}
```

关键断言：业务码为 200

清理结果：成功

## 未验证范围

- 无

## 测试总结

通过：1；失败：0；跳过：0；未执行：0。
"""


class ValidateE2ETest(unittest.TestCase):
    def test_accepts_report_with_scenario_and_observation_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(VALID_REPORT, encoding="utf-8")
            self.assertEqual([], validate(report))

    def test_rejects_report_without_scenario_status(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(VALID_REPORT.replace("| 通过 |", "|  |"), encoding="utf-8")
            self.assertIn("场景总览必须包含", "\n".join(validate(report)))

    def test_rejects_empty_unverified_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(VALID_REPORT.replace("- 无", ""), encoding="utf-8")
            self.assertIn("未验证范围不能是空章节", "\n".join(validate(report)))

    def test_rejects_response_without_formatted_json(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(VALID_REPORT.replace("返回值 JSON：", "响应摘要："), encoding="utf-8")
            self.assertIn("返回值 JSON", "\n".join(validate(report)))

    def test_rejects_scenario_without_independent_command(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(VALID_REPORT.replace("命令或脚本（本场景可单独执行；可直接包含 token、Cookie 等凭证）：\n\n```bash\ncurl --max-time 10 -H 'Authorization: Bearer test-token' https://example.test/items\n```\n", ""), encoding="utf-8")
            self.assertIn("必须包含可单独执行的命令或脚本", "\n".join(validate(report)))

    def test_requires_json_for_each_scenario(self):
        report_text = VALID_REPORT + """

### S02 查询

前置条件：环境可用
数据副作用：无
结果：HTTP 200
命令或脚本：
```bash
curl https://example.test/items/2
```
关键断言：业务码为 200
清理结果：无
"""
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "e2e-test.md"
            report.write_text(report_text, encoding="utf-8")
            self.assertIn("场景 S02 必须包含格式化的返回值 JSON", "\n".join(validate(report)))


if __name__ == "__main__":
    unittest.main()
