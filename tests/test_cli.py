"""CLI の安全装置のテスト。

`clean --all` は作業ディレクトリを丸ごと消すので、build.workdir の
打ち間違いでプロジェクトやホームを消さないことを確認する。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import cli  # noqa: E402


class CleanupSafetyTest(unittest.TestCase):
    def test_build_subdirectory_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "project"
            base.mkdir()
            self.assertTrue(cli._cleanup_is_safe(base / "build", base))

    def test_project_directory_is_not_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "project"
            base.mkdir()
            self.assertFalse(cli._cleanup_is_safe(base, base))

    def test_ancestor_of_the_project_is_not_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "project"
            base.mkdir()
            self.assertFalse(cli._cleanup_is_safe(Path(tmp), base))

    def test_filesystem_root_is_not_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "project"
            base.mkdir()
            self.assertFalse(cli._cleanup_is_safe(Path("/"), base))


if __name__ == "__main__":
    unittest.main()
