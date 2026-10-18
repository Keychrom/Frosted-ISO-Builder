"""翻訳の抜けを検出するテスト。

「英語モードで走らせたときに日本語が残っていないか」を実際の出力で
確かめる。静的にソースを走査するより確実で、利用者が見るものそのものを
検証できる。

日本語が混じってよいのは、レシピの値やファイルパスなど「利用者が自分で
書いたデータ」だけ。それらは出力に出ても日本語ではないことが多いが、
日本語のレシピを使えば出る。このテストで使うレシピは英語のみで組んである。
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import cli, i18n, ui  # noqa: E402
from frosted.i18n_en import EN, PATTERNS, PREFIXES  # noqa: E402

#: 日本語 (ひらがな・カタカナ・漢字) と全角記号
CJK = re.compile(r"[぀-ゟ゠-ヿ一-鿿　-〿＀-￯]")


@contextlib.contextmanager
def english():
    """英語モードにする。"""
    previous = i18n.get_language()
    i18n.set_language("en")
    ui.init_color(force=False)
    try:
        yield
    finally:
        i18n.set_language(previous)


@contextlib.contextmanager
def captured():
    """stdout と stderr を捕まえる。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


def run_cli(argv: list[str]) -> tuple[int, str]:
    """CLI を走らせて (終了コード, 出力) を返す。"""
    with english(), captured() as (out, err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse の --help / --version
            code = int(exc.code or 0)
    return code, out.getvalue() + err.getvalue()


class LanguageDetectionTest(unittest.TestCase):
    def test_japanese_locale_selects_japanese(self) -> None:
        with mock.patch.dict(os.environ, {"LANG": "ja_JP.UTF-8"}, clear=False):
            for name in ("LC_ALL", "LC_MESSAGES", "FROSTED_LANG"):
                os.environ.pop(name, None)
            self.assertEqual(i18n.detect_language(), "ja")

    def test_other_locales_select_english(self) -> None:
        for locale in ("en_US.UTF-8", "de_DE.UTF-8", "C", "POSIX", "C.UTF-8"):
            with self.subTest(locale=locale), mock.patch.dict(
                os.environ, {"LANG": locale}, clear=False
            ):
                for name in ("LC_ALL", "LC_MESSAGES", "FROSTED_LANG"):
                    os.environ.pop(name, None)
                self.assertEqual(i18n.detect_language(), "en")

    def test_explicit_override_wins(self) -> None:
        with mock.patch.dict(
            os.environ, {"LANG": "de_DE.UTF-8", "FROSTED_LANG": "ja"}, clear=False
        ):
            self.assertEqual(i18n.detect_language(), "ja")

    def test_lc_all_takes_precedence_over_lang(self) -> None:
        env = {"LANG": "en_US.UTF-8", "LC_ALL": "ja_JP.UTF-8"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("FROSTED_LANG", None)
            self.assertEqual(i18n.detect_language(), "ja")

    def test_unsupported_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            i18n.set_language("fr")


class TranslationLookupTest(unittest.TestCase):
    def test_exact_match(self) -> None:
        with english():
            self.assertEqual(
                i18n.t("操作を中断しました。"), EN["操作を中断しました。"]
            )

    def test_prefix_match_keeps_the_value(self) -> None:
        """値の部分は翻訳せず、そのまま残すこと。"""
        with english():
            result = i18n.t("使えない名前です: 'My Linux'")
            self.assertTrue(result.startswith(PREFIXES["使えない名前です"]))
            self.assertIn("'My Linux'", result)

    def test_unknown_text_is_returned_unchanged(self) -> None:
        with english():
            self.assertEqual(i18n.t("some data 123"), "some data 123")

    def test_japanese_mode_returns_the_original(self) -> None:
        i18n.set_language("ja")
        self.assertEqual(i18n.t("操作を中断しました。"), "操作を中断しました。")

    def test_format_placeholders_are_filled(self) -> None:
        with english():
            self.assertEqual(
                i18n.t("1 から {count} の番号で答えてください。", count=3),
                EN["1 から {count} の番号で答えてください。"].format(count=3),
            )

    def test_catalog_placeholders_match_the_source(self) -> None:
        """訳のプレースホルダが原文と食い違うと、値が埋まらずに表示される。"""
        pattern = re.compile(r"\{(\w+)\}")
        for source, translated in EN.items():
            with self.subTest(source=source[:40]):
                self.assertEqual(
                    set(pattern.findall(source)),
                    set(pattern.findall(translated)),
                    f"プレースホルダが一致しません: {source!r} -> {translated!r}",
                )

    def test_patterns_do_not_mangle_english_text(self) -> None:
        for pattern, _replacement in PATTERNS:
            with self.subTest(pattern=pattern.pattern):
                self.assertIsNone(pattern.search("Some plain English text 123"))


class CliOutputIsTranslatedTest(unittest.TestCase):
    """英語モードで日本語が出力に残っていないこと。"""

    def _assert_no_japanese(self, label: str, text: str) -> None:
        leftovers = [
            line.strip()
            for line in text.splitlines()
            if CJK.search(line)
        ]
        self.assertEqual(
            leftovers,
            [],
            f"{label} の出力に日本語が残っています:\n" + "\n".join(leftovers),
        )

    def test_top_level_help(self) -> None:
        _code, text = run_cli(["--help"])
        self._assert_no_japanese("--help", text)

    def test_every_subcommand_help(self) -> None:
        commands = sorted(cli.COMMANDS)
        for command in commands:
            with self.subTest(command=command):
                _code, text = run_cli([command, "--help"])
                self._assert_no_japanese(f"{command} --help", text)

    def test_no_command_prints_help(self) -> None:
        _code, text = run_cli([])
        self._assert_no_japanese("引数なし", text)

    def test_doctor_output(self) -> None:
        _code, text = run_cli(["doctor", "--no-network"])
        self._assert_no_japanese("doctor", text)

    def test_validate_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Path(tmp) / "recipe.toml"
            recipe.write_text(
                'version = 1\n[iso]\nname = "citest"\n', encoding="utf-8"
            )
            _code, text = run_cli(
                ["validate", str(recipe), "--no-network", "--no-root"]
            )
        self._assert_no_japanese("validate", text)

    def test_validate_reports_errors_in_english(self) -> None:
        """検証エラーは英語利用者がいちばん見る出力なので、必ず訳すこと。"""
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Path(tmp) / "recipe.toml"
            recipe.write_text(
                'version = 1\n[iso]\nname = "Bad Name"\n[build]\njobs = 4\n',
                encoding="utf-8",
            )
            code, text = run_cli(["validate", str(recipe), "--no-network", "--no-root"])

        self.assertEqual(code, 1)
        self._assert_no_japanese("validate (エラーあり)", text)

    def test_show_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Path(tmp) / "recipe.toml"
            recipe.write_text(
                'version = 1\n[iso]\nname = "citest"\n', encoding="utf-8"
            )
            _code, text = run_cli(["show", str(recipe)])
        self._assert_no_japanese("show", text)

    def test_show_output_with_custom_packages_and_swap(self) -> None:
        """新しい設定項目も英語で表示されること。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deb = root / "hello_1.0_amd64.deb"
            deb.write_bytes(b"deb")
            recipe = root / "recipe.toml"
            recipe.write_text(
                "version = 1\n"
                '[iso]\nname = "citest"\n'
                "[packages]\n"
                f'local = ["{deb.as_posix()}"]\n'
                "[apt]\n"
                "preferences = '''Package: *\n"
                "Pin: release a=trixie\n"
                "Pin-Priority: 100\n"
                "'''\n"
                "[boot]\n"
                'install_append = "quiet"\n'
                "[binary]\n"
                'swap_file_path = "/swapfile"\n'
                "swap_file_size = 1024\n",
                encoding="utf-8",
            )
            _code, text = run_cli(["show", str(recipe)])
        self._assert_no_japanese("show (追加設定)", text)

    def test_presets_output(self) -> None:
        _code, text = run_cli(["presets"])
        self._assert_no_japanese("presets", text)

    def test_preset_detail_output(self) -> None:
        for name in ("minimal", "rescue", "desktop", "kiosk", "dev"):
            with self.subTest(preset=name):
                _code, text = run_cli(["presets", name])
                self._assert_no_japanese(f"presets {name}", text)

    def test_verify_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "image.iso"
            iso.write_bytes(b"not really an iso")
            _code, text = run_cli(["verify", str(iso)])
        self._assert_no_japanese("verify", text)

    def test_missing_recipe_error(self) -> None:
        _code, text = run_cli(["validate", "/nonexistent/recipe.toml"])
        self._assert_no_japanese("存在しないレシピ", text)


class WizardIsTranslatedTest(unittest.TestCase):
    """ウィザードは主経路なので、質問文と要約が英語になること。"""

    def _run(self) -> str:
        from tests.test_wizard import WizardHarness
        from frosted import wizard

        with english():
            harness = WizardHarness()
            recipe = harness.run(preset_key="desktop", name="englishtest")
            text = harness.output.getvalue()

        with english(), contextlib.redirect_stdout(buffer := io.StringIO()):
            for label, value in wizard.summarize(recipe):
                ui.out(f"{label}: {value}")
        return text + buffer.getvalue()

    def test_wizard_output(self) -> None:
        text = self._run()
        leftovers = [line.strip() for line in text.splitlines() if CJK.search(line)]
        self.assertEqual(
            leftovers,
            [],
            "ウィザードの出力に日本語が残っています:\n" + "\n".join(leftovers),
        )

    def test_summary_labels_are_translated(self) -> None:
        from tests.test_wizard import WizardHarness
        from frosted import wizard

        with english():
            recipe = WizardHarness().run(preset_key="minimal", name="englishtest")
            rows = wizard.summarize(recipe)

        for label, value in rows:
            with self.subTest(label=label):
                self.assertIsNone(CJK.search(label), f"項目名が日本語: {label}")
                if "Live User" not in value and "/" not in value:
                    self.assertIsNone(CJK.search(value), f"値が日本語: {value}")


class GeneratedFilesAreTranslatedTest(unittest.TestCase):
    """生成する設定ファイルも英語で出せること。"""

    def test_auto_config_comments(self) -> None:
        from tests.test_livebuild import Project, _basic_recipe

        with english(), tempfile.TemporaryDirectory() as tmp:
            recipe = _basic_recipe("englishtest")
            with Project(recipe) as project:
                project.generate()
                config = (project.workdir() / "auto" / "config").read_text(
                    encoding="utf-8"
                )
                readme = (project.workdir() / "README.build.md").read_text(
                    encoding="utf-8"
                )

        for name, text in (("auto/config", config), ("README.build.md", readme)):
            with self.subTest(file=name):
                leftovers = [
                    line.strip() for line in text.splitlines() if CJK.search(line)
                ]
                self.assertEqual(
                    leftovers,
                    [],
                    f"{name} に日本語が残っています:\n" + "\n".join(leftovers),
                )

    def test_hooks_are_translated_for_every_preset_and_desktop(self) -> None:
        """全プリセット×全デスクトップの組み合わせを確認する。

        1 通りだけ試すと、自動ログインのフックのように特定の構成でしか
        生成されないファイルを見落とす (実際に見落とした)。
        """
        from frosted.catalog import DESKTOPS, PRESETS, apply_preset
        from tests.test_livebuild import Project, _basic_recipe

        newline = chr(10)

        for preset in PRESETS:
            for desktop in DESKTOPS:
                with self.subTest(preset=preset, desktop=desktop):
                    recipe = _basic_recipe("englishtest")
                    recipe.desktop.environment = desktop
                    apply_preset(recipe, preset)
                    # フックの分岐をひととおり通す
                    recipe.user.autologin = True
                    recipe.user.sudo = True
                    recipe.user.default_groups = "sudo"
                    recipe.user.password = "secret"
                    recipe.ssh.enable_server = True
                    recipe.packages.exclude = ["vim"]

                    with english():
                        with Project(recipe) as project:
                            project.generate()
                            workdir = project.workdir()
                            files = {
                                "auto/config": workdir / "auto" / "config",
                                "README.build.md": workdir / "README.build.md",
                            }
                            for path in (workdir / "config" / "hooks" / "live").glob(
                                "*"
                            ):
                                files[path.name] = path
                            contents = {
                                name: path.read_text(encoding="utf-8")
                                for name, path in files.items()
                            }

                    name_prefix = f"{preset}/{desktop} の "
                    for name, content in contents.items():
                        leftovers = [
                            line.strip()
                            for line in content.splitlines()
                            if CJK.search(line)
                        ]
                        self.assertEqual(
                            leftovers,
                            [],
                            name_prefix
                            + name
                            + " に日本語が残っています:"
                            + newline
                            + newline.join(leftovers),
                        )


if __name__ == "__main__":
    unittest.main()
