"""install.sh の基本的な動作のテスト。

apt を実際に叩く部分は root とネットワークが要るので試さない。
ここでは「ヘルプと引数解析が壊れていないこと」だけを確認する。
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SH = shutil.which("sh") or shutil.which("bash")


@unittest.skipIf(SH is None, "sh が無いため省略")
class InstallScriptTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [SH, "install.sh", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_syntax(self) -> None:
        proc = subprocess.run(
            [SH, "-n", "install.sh"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_help_lists_both_install_options(self) -> None:
        proc = self._run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--with-deps", proc.stdout)
        self.assertIn("--with-additional", proc.stdout)
        self.assertIn("--uninstall", proc.stdout)

    def test_unknown_option_is_rejected(self) -> None:
        proc = self._run("--with-dependencies")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--with-dependencies", proc.stderr)


if __name__ == "__main__":
    unittest.main()
