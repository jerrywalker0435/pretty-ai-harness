from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "install/CODEX_INSTALL_PROMPT.template.md"


class InstallPromptTest(unittest.TestCase):
    def test_pretty_common_update_uses_a_recoverable_swap(self) -> None:
        content = PROMPT.read_text(encoding="utf-8")

        self.assertIn("PRETTY_SWAP_ROOT=", content)
        self.assertIn('trap pretty_restore_previous EXIT', content)
        self.assertIn('mv "$PRETTY_COMMON_TARGET" "$PRETTY_BACKUP_PATH"', content)
        self.assertNotIn('rm -rf "$PRETTY_TARGET_SKILLS_DIR/pretty-common"', content)

    def test_upgrade_handles_removed_legacy_skills_explicitly(self) -> None:
        content = PROMPT.read_text(encoding="utf-8")

        self.assertIn("refactor", content)
        self.assertIn("verification-before-completion", content)
        self.assertIn("保留这些额外 Skill", content)
        self.assertIn("删除这些旧版遗留 Skill", content)
        self.assertIn("pretty-writing-plan", content)
        self.assertIn("pretty-executing-plan", content)
        self.assertIn("这四个目录", content)

    def test_current_distribution_uses_three_pretty_skills(self) -> None:
        content = PROMPT.read_text(encoding="utf-8")
        self.assertIn("pretty-writing-prd`、`pretty-writing-design`、`pretty-executing", content)
        self.assertIn("共 13 个可注册 Skill", content)


if __name__ == "__main__":
    unittest.main()
