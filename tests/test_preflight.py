"""ビルド前の環境診断のテスト。

ここは「動くはずの環境を動かないと誤判定する」と、利用者が存在しない
パッケージを入れようとして時間を溶かす。実際に Debian の VM で
`debootstrap` と `chroot` を「見つかりません」と誤報した。どちらも
/usr/sbin にあり、一般ユーザーの PATH には入っていないのが原因だった。

そのため、PATH に無くても標準のディレクトリにあれば見つけること、
そして apt のパッケージ名の案内が正しいことを重点的に確認する。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import preflight, runner  # noqa: E402
from frosted.recipe import Recipe  # noqa: E402


class WhichTest(unittest.TestCase):
    def test_finds_something_that_is_on_path(self) -> None:
        # python 自身は必ず PATH にある
        self.assertIsNotNone(runner.which("python" if os.name == "nt" else "sh"))

    def test_returns_none_for_a_missing_command(self) -> None:
        self.assertIsNone(runner.which("definitely-not-a-real-command-xyz"))

    def test_finds_a_command_outside_path(self) -> None:
        """PATH に無くても標準のディレクトリにあれば見つけること。

        Debian の /usr/sbin がこれにあたる。ここを見落とすと
        debootstrap や chroot を「無い」と誤判定する。
        """
        with tempfile.TemporaryDirectory() as tmp:
            fake_dir = Path(tmp)
            target = fake_dir / "sbin-only-command"
            target.write_text("#!/bin/sh\n", encoding="utf-8")

            # PATH からは見つからない状態にする
            with mock.patch.object(runner.shutil, "which", return_value=None):
                self.assertIsNone(
                    runner.which("sbin-only-command"),
                    "PATH に無いコマンドが見つかってしまっている",
                )
                with mock.patch.object(
                    runner, "FALLBACK_DIRS", (str(fake_dir),)
                ):
                    self.assertEqual(
                        runner.which("sbin-only-command"), str(target)
                    )

    def test_standard_directories_are_searched(self) -> None:
        """Debian で問題になったディレクトリが候補に入っていること。"""
        for directory in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
            with self.subTest(directory=directory):
                self.assertIn(directory, runner.FALLBACK_DIRS)

    def test_fallback_ignores_non_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(runner.shutil, "which", return_value=None):
                with mock.patch.object(runner, "FALLBACK_DIRS", (tmp,)):
                    self.assertIsNone(runner.which("nothing-here"))


class AptHintTest(unittest.TestCase):
    def test_command_names_in_packages_mapping(self) -> None:
        """コマンド名とパッケージ名が違うものを正しく案内すること。

        `chroot` という名前のパッケージは存在しないので、
        `sudo apt install chroot` と案内してはいけない。
        """
        cases = {
            "lb": "live-build",
            "mksquashfs": "squashfs-tools",
            "uuidgen": "uuid-runtime",
            "chroot": "coreutils",
            "mount": "util-linux",
        }
        for command, package in cases.items():
            with self.subTest(command=command):
                hint = preflight._apt_hint([command])
                self.assertIn(package, hint)
                self.assertNotIn(f" {command} ", f" {hint} ")

    def test_unknown_command_is_passed_through(self) -> None:
        self.assertIn("some-tool", preflight._apt_hint(["some-tool"]))

    def test_hint_is_sorted_and_deduplicated(self) -> None:
        hint = preflight._apt_hint(["xorriso", "xorriso", "lb"])
        self.assertEqual(hint.count("xorriso"), 1)
        self.assertIn("apt install", hint)


class ReportTest(unittest.TestCase):
    def _report(self, statuses: list[str]) -> preflight.PreflightReport:
        report = preflight.PreflightReport()
        for index, status in enumerate(statuses):
            report.checks.append(preflight.Check(f"check{index}", status, "detail"))
        return report

    def test_failures_and_warnings_are_split(self) -> None:
        report = self._report(["ok", "warn", "fail", "skip", "warn"])
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(len(report.warnings), 2)
        self.assertFalse(report.passed)

    def test_warnings_alone_still_pass(self) -> None:
        report = self._report(["ok", "warn", "skip"])
        self.assertTrue(report.passed)

    def test_missing_tools_produce_a_failure(self) -> None:
        """必須ツールが本当に無いときは失敗になること (誤検出と区別する)。"""
        # preflight は which を直接インポートしているので、
        # runner 側ではなく preflight 側を差し替える
        with mock.patch.object(preflight, "which", return_value=None):
            checks = preflight._check_tools()

        statuses = {check.name: check.status for check in checks}
        self.assertEqual(statuses["必須ツール"], "fail")
        self.assertEqual(statuses["任意ツール"], "warn")

    def test_all_tools_found_produces_success(self) -> None:
        with mock.patch.object(
            preflight, "which", return_value="/usr/bin/whatever"
        ):
            checks = preflight._check_tools()

        statuses = {check.name: check.status for check in checks}
        self.assertEqual(statuses["必須ツール"], "ok")
        self.assertEqual(statuses["任意ツール"], "ok")

    def test_tools_in_sbin_are_not_reported_missing(self) -> None:
        """VM で起きた誤検出そのものを再現して確認する。

        PATH には無いが /usr/sbin にはある、という状態を作り、
        「必須ツールが見つかりません」で失敗にならないこと。
        """
        with tempfile.TemporaryDirectory() as tmp:
            # /usr/sbin を模したディレクトリに必須ツールを全部置く
            for command, _description in preflight.MANDATORY_TOOLS:
                (Path(tmp) / command).write_text("#!/bin/sh\n", encoding="utf-8")

            with mock.patch.object(runner.shutil, "which", return_value=None):
                with mock.patch.object(runner, "FALLBACK_DIRS", (tmp,)):
                    # preflight 側の which を、フォールバック込みの本物に差し替える
                    with mock.patch.object(
                        preflight, "which", side_effect=runner.which
                    ):
                        checks = preflight._check_tools()

        statuses = {check.name: check.status for check in checks}
        self.assertEqual(
            statuses["必須ツール"],
            "ok",
            "PATH に無いだけで「無い」と判定している",
        )
        # 任意ツールは本当に無いので警告どまり
        self.assertEqual(statuses["任意ツール"], "warn")


class DiskCheckTest(unittest.TestCase):
    def test_reports_a_size(self) -> None:
        recipe = Recipe()
        check = preflight._check_disk(recipe)
        self.assertIn(check.status, ("ok", "warn", "fail", "skip"))
        if check.status != "skip":
            self.assertIn("GiB", check.detail)


if __name__ == "__main__":
    unittest.main()
