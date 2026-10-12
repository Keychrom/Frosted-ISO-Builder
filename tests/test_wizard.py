"""対話ウィザードのテスト。

ウィザードは利用者が最初に触るところなので、入力関数を差し替えて
最後まで通しで走らせ、組み上がったレシピを検証する。

とくに「プリセットが決めた値をウィザードが上書きしないこと」は大事。
キオスクのように意図的に権限を絞っているプリセットの設定が、
Enter を押しただけで元に戻ってしまうと気づきにくい。
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import ui, wizard  # noqa: E402
from frosted.catalog import PRESETS  # noqa: E402


def _ask(queue):
    def impl(label, default=None, validate=None, allow_empty=False):
        if queue:
            return queue.pop(0)
        return default if default is not None else ""

    return impl


def _ask_bool(queue):
    def impl(label, default=False):
        if queue:
            value = queue.pop(0)
            if isinstance(value, bool):
                return value
        return default

    return impl


def _ask_choice(queue):
    def impl(label, options, default_index=0, descriptions=True):
        if queue:
            value = queue.pop(0)
            if isinstance(value, int):
                return options[value][0]
            return value
        return options[default_index][0]

    return impl


def _ask_list(queue):
    def impl(label, default=()):
        if queue:
            return list(queue.pop(0))
        return list(default)

    return impl


def _ask_password(queue):
    def impl(label):
        if queue:
            return queue.pop(0)
        return ""

    return impl


class WizardHarness:
    """入力関数を差し替えてウィザードを走らせる。

    answers に書かなかった質問は既定値で答えたことになる。
    """

    def __init__(self, answers: dict[str, list] | None = None) -> None:
        self.answers = {
            name: list(values) for name, values in (answers or {}).items()
        }

    def run(self, **kwargs):
        patches = {
            "ask": _ask(self.answers.get("ask", [])),
            "ask_bool": _ask_bool(self.answers.get("ask_bool", [])),
            "ask_choice": _ask_choice(self.answers.get("ask_choice", [])),
            "ask_list": _ask_list(self.answers.get("ask_list", [])),
            "ask_password": _ask_password(self.answers.get("ask_password", [])),
        }
        # 捕捉した出力は self.output から読めるようにしておく。
        # 以前は呼び出し側で redirect_stdout していたが、ここで上書きされる
        # ため外側のバッファが空のままになり、翻訳漏れを見逃していた。
        self.output = io.StringIO()
        with mock.patch.multiple(ui, **patches), contextlib.redirect_stdout(
            self.output
        ):
            return wizard.run(**kwargs)


class PresetDefaultsTest(unittest.TestCase):
    """プリセットの意図がウィザードに消されないこと。"""

    def test_kiosk_keeps_sudo_disabled(self) -> None:
        recipe = WizardHarness().run(preset_key="kiosk", name="lobby")

        self.assertFalse(
            recipe.user.sudo,
            "キオスクは sudo を与えない設定なのに、ウィザードが有効に戻している",
        )
        self.assertTrue(recipe.user.autologin)

    def test_rescue_keeps_ssh_enabled(self) -> None:
        recipe = WizardHarness().run(preset_key="rescue", name="rescue")
        self.assertTrue(recipe.ssh.enable_server)

    def test_every_preset_survives_the_wizard(self) -> None:
        for key in PRESETS:
            with self.subTest(preset=key):
                recipe = WizardHarness().run(preset_key=key, name=f"test-{key}")
                self.assertEqual(recipe.iso.name, f"test-{key}")

                # 適用前後の差がウィザードで失われていないこと
                expected = PRESETS[key]
                reference = recipe.__class__()
                expected.apply(reference)
                self.assertEqual(
                    recipe.user.sudo, reference.user.sudo, f"{key}: sudo が変わった"
                )
                self.assertEqual(
                    recipe.user.autologin,
                    reference.user.autologin,
                    f"{key}: 自動ログインが変わった",
                )
                self.assertEqual(
                    recipe.ssh.enable_server,
                    reference.ssh.enable_server,
                    f"{key}: SSH が変わった",
                )

    def test_minimal_has_no_desktop(self) -> None:
        recipe = WizardHarness().run(preset_key="minimal", name="tiny")
        self.assertEqual(recipe.desktop.environment, "none")


class AnswerApplicationTest(unittest.TestCase):
    def test_name_and_version_are_applied(self) -> None:
        harness = WizardHarness({"ask": ["mylinux", "2.5"]})
        recipe = harness.run()
        self.assertEqual(recipe.iso.name, "mylinux")
        self.assertEqual(recipe.iso.version, "2.5")

    def test_distribution_and_architecture_selection(self) -> None:
        harness = WizardHarness(
            {"ask_choice": ["bookworm", "arm64", "minimal", "none", "none"]}
        )
        recipe = harness.run(name="armsrv")
        self.assertEqual(recipe.iso.distribution, "bookworm")
        self.assertEqual(recipe.iso.architecture, "arm64")

    def test_desktop_selection_replaces_preset_choice(self) -> None:
        # 3 番目の ask_choice がデスクトップ環境
        harness = WizardHarness({"ask_choice": [0, 0, 0, "gnome", "none"]})
        recipe = harness.run(name="gnomebox")
        self.assertEqual(recipe.desktop.environment, "gnome")

    def test_extra_packages_are_added(self) -> None:
        harness = WizardHarness({"ask_list": [["vim", "curl", "tmux"], []]})
        recipe = harness.run(name="pkgtest")
        for name in ("vim", "curl", "tmux"):
            self.assertIn(name, recipe.packages.include)

    def test_autologin_off_asks_for_a_password(self) -> None:
        harness = WizardHarness(
            {"ask_bool": [False, True], "ask_password": ["secret"]}
        )
        recipe = harness.run(name="locked")
        self.assertFalse(recipe.user.autologin)
        self.assertEqual(recipe.user.password, "secret")

    def test_autologin_on_keeps_password_empty(self) -> None:
        recipe = WizardHarness().run(name="easy")
        self.assertTrue(recipe.user.autologin)
        self.assertEqual(recipe.user.password, "")

    def test_ssh_enabled_with_keys(self) -> None:
        harness = WizardHarness(
            {"ask_bool": [True, True, True, True], "ask_list": [[], ["/tmp/key.pub"]]}
        )
        recipe = harness.run(name="sshtest")
        self.assertTrue(recipe.ssh.enable_server)
        self.assertEqual(recipe.ssh.authorized_keys, ["/tmp/key.pub"])


class ValidatorTest(unittest.TestCase):
    def test_iso_name_validator(self) -> None:
        self.assertIsNone(wizard._validate_iso_name("mylinux"))
        self.assertIsNotNone(wizard._validate_iso_name("My Linux"))
        self.assertIsNotNone(wizard._validate_iso_name("-bad"))

    def test_username_validator(self) -> None:
        self.assertIsNone(wizard._validate_username("user"))
        self.assertIsNotNone(wizard._validate_username("root"))
        self.assertIsNotNone(wizard._validate_username("Bad"))

    def test_locale_validator(self) -> None:
        self.assertIsNone(wizard._validate_locale("ja_JP.UTF-8"))
        self.assertIsNone(wizard._validate_locale("C.UTF-8"))
        self.assertIsNotNone(wizard._validate_locale("nonsense!!"))


class SummaryTest(unittest.TestCase):
    def test_summary_mentions_the_important_settings(self) -> None:
        harness = WizardHarness()
        recipe = harness.run(preset_key="kiosk", name="lobby")
        labels = [label for label, _ in wizard.summarize(recipe)]

        for expected in ("名前", "出力ファイル", "デスクトップ", "sudo", "SSH"):
            self.assertIn(expected, labels)

    def test_suggested_path_uses_the_iso_name(self) -> None:
        recipe = WizardHarness().run(name="named-test")
        self.assertEqual(wizard.suggest_path(recipe).name, "named-test.toml")


if __name__ == "__main__":
    unittest.main()
