"""外部コマンド実行ヘルパーのテスト。

lb build は数十分かかるので、既定で進捗が画面に流れないとフリーズしたように
見える。ログに残すことと画面に出すことを別々に制御できているか確認する。
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import runner as runner_module  # noqa: E402
from frosted.runner import run_streaming  # noqa: E402

SH = shutil.which("sh") or shutil.which("bash")


@unittest.skipIf(SH is None, "sh が見つからないため省略")
class StreamingTest(unittest.TestCase):
    def _run(self, *, quiet: bool) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            screen = io.StringIO()
            with contextlib.redirect_stdout(screen):
                code = run_streaming(
                    [SH, "-c", "echo BUILD-OUTPUT"],
                    log_path=log_path,
                    echo=False,
                    quiet=quiet,
                )
            return code, screen.getvalue(), log_path.read_text(encoding="utf-8")

    def test_output_is_streamed_even_when_command_echo_is_off(self) -> None:
        code, screen, log = self._run(quiet=False)
        self.assertEqual(code, 0)
        self.assertIn("BUILD-OUTPUT", screen)
        self.assertIn("BUILD-OUTPUT", log)

    def test_quiet_hides_screen_output_but_keeps_the_log(self) -> None:
        code, screen, log = self._run(quiet=True)
        self.assertEqual(code, 0)
        self.assertNotIn("BUILD-OUTPUT", screen)
        self.assertIn("BUILD-OUTPUT", log)


class PrivilegedTest(unittest.TestCase):
    def test_sudo_does_not_preserve_the_environment(self) -> None:
        """sudoers によっては -E が拒否されるので使わない。"""
        from unittest import mock

        with mock.patch.object(runner_module, "is_root", return_value=False):
            with mock.patch.object(
                runner_module, "which", return_value="/usr/bin/sudo"
            ):
                self.assertEqual(
                    runner_module.privileged(["lb", "config"]),
                    ["/usr/bin/sudo", "lb", "config"],
                )


if __name__ == "__main__":
    unittest.main()
