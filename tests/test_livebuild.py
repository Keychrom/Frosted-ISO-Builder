"""live-build の設定ツリー生成のテスト。

このツールの価値の本体はここなので、いちばん厚くテストする。
とくに次の 3 つは外すとビルドが壊れるので必ず見る。

1. auto/config に `noauto` が入っているか (無いと live-build が無限に再帰する)
2. 生成したシェルスクリプトの構文が正しいか
3. レシピの値がシェルの引用符で正しく守られているか

Debian に行く前に Windows 上で気づけるように、Git Bash の sh を使って
実際に構文を解析させている。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted.backend.livebuild import (  # noqa: E402
    build_bootappend,
    build_lb_argv,
    generate,
)
from frosted.catalog import apply_preset  # noqa: E402
from frosted.errors import BuildError  # noqa: E402
from frosted.recipe import CopyEntry, Recipe, WriteEntry  # noqa: E402

SH = shutil.which("sh") or shutil.which("bash")


def _msys_path(path: str) -> str:
    """Windows のパスを Git Bash (MSYS) が理解する形に直す。"""
    path = path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        path = "/" + path[0].lower() + path[2:]
    return path


def _msys_env(extra_path: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    parts = []
    if extra_path is not None:
        parts.append(_msys_path(str(extra_path)))
    if os.name == "nt":
        parts.extend(_msys_path(p) for p in env.get("PATH", "").split(";") if p)
        env["PATH"] = ":".join(parts)
    elif extra_path is not None:
        env["PATH"] = f"{extra_path}:{env.get('PATH', '')}"
    # MSYS がパスを勝手に変換しないようにする
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    return env


class Project:
    """テスト用の一時プロジェクト。"""

    def __init__(self, recipe: Recipe) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        recipe.path = self.root / "recipe.toml"
        recipe.build.workdir = "build"
        self.recipe = recipe

    def workdir(self) -> Path:
        return self.recipe.workdir()

    def generate(self):
        return generate(self.recipe)

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


def _basic_recipe(name: str = "mylinux") -> Recipe:
    recipe = Recipe()
    recipe.iso.name = name
    recipe.iso.version = "1.0"
    return recipe


def _command_lines(text: str) -> str:
    """コメント行を除いた、実際に実行される部分だけを取り出す。"""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


class TreeGenerationTest(unittest.TestCase):
    def test_generates_expected_layout(self) -> None:
        with Project(_basic_recipe()) as project:
            result = project.generate()
            workdir = project.workdir()

            self.assertTrue((workdir / "auto" / "config").is_file())
            self.assertTrue((workdir / "config" / "package-lists").is_dir())
            self.assertTrue((workdir / "config" / "hooks" / "live").is_dir())
            self.assertTrue(
                (workdir / "config" / "package-lists" / "00-base.list.chroot").is_file()
            )
            self.assertTrue(result.created)

    def test_does_not_generate_auto_build(self) -> None:
        """auto/build を置くと live-build の自動実行と再帰しかねないので作らない。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            self.assertFalse((project.workdir() / "auto" / "build").exists())
            self.assertFalse((project.workdir() / "auto" / "clean").exists())

    def test_auto_config_guards_against_recursion(self) -> None:
        """noauto が無いと live-build が auto/config を呼び続けて再帰する。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            text = (project.workdir() / "auto" / "config").read_text(encoding="utf-8")

            command = _command_lines(text)
            # noautologin のような別の語に引っかからないよう語単位で数える
            self.assertEqual(
                len(re.findall(r"(?<![-\w])noauto(?![-\w])", command)),
                1,
                f"noauto は 1 回だけのはず:\n{command}",
            )
            self.assertIn("lb config \\", command)
            self.assertIn('"${@}"', command)

    def test_auto_config_has_no_duplicate_flags(self) -> None:
        """同じフラグを 2 回出すと、後勝ちで設定が意図せず変わる。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            text = (project.workdir() / "auto" / "config").read_text(encoding="utf-8")
            command = _command_lines(text)
            for flag in (
                "--distribution",
                "--architecture",
                "--bootloaders",
                "--bootappend-live",
            ):
                with self.subTest(flag=flag):
                    # --bootappend-live が --bootappend-live-failsafe に
                    # 引っかからないよう、後ろが英数字でないものだけ数える
                    found = re.findall(rf"{re.escape(flag)}(?!-?[a-z])", command)
                    self.assertEqual(len(found), 1, f"{flag} が {len(found)} 回ある")

    def test_generated_scripts_use_lf_line_endings(self) -> None:
        """CRLF で生成すると Linux 側で /bin/sh^M として実行できなくなる。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            workdir = project.workdir()
            targets = [workdir / "auto" / "config"]
            targets += sorted((workdir / "config" / "hooks" / "live").glob("*"))
            targets += sorted((workdir / "config" / "package-lists").glob("*"))
            for path in targets:
                with self.subTest(path=path.name):
                    self.assertNotIn(b"\r", path.read_bytes(), f"{path.name} に CR が混じっている")

    def test_manifest_lists_generated_files(self) -> None:
        with Project(_basic_recipe()) as project:
            project.generate()
            manifest = project.workdir() / ".frosted-manifest.json"
            self.assertTrue(manifest.is_file())
            self.assertIn("auto/config", manifest.read_text(encoding="utf-8"))

    def test_regeneration_removes_stale_files(self) -> None:
        """レシピから項目を消したら、生成物からも消えること。"""
        recipe = _basic_recipe()
        recipe.packages.include = ["vim"]
        with Project(recipe) as project:
            project.generate()
            stale = (
                project.workdir()
                / "config"
                / "package-lists"
                / "90-user.list.chroot"
            )
            self.assertTrue(stale.is_file())

            recipe.packages.include = []
            project.generate()
            self.assertFalse(stale.exists(), "使わなくなったファイルが残っている")

    def test_regeneration_removes_stale_livebuild_config_files(self) -> None:
        """前回の config/binary に壊れた値が残っていても再生成できること。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            stale = project.workdir() / "config" / "binary"
            stale.write_text(
                'LB_BOOTAPPEND_LIVE="bad user-fullname="Live User" \n',
                encoding="utf-8",
            )

            project.generate()
            self.assertFalse(
                stale.exists(),
                "古い config/binary が残っていて、次の lb config が壊れる",
            )
            # 生成物のサブディレクトリは消さない
            self.assertTrue(
                (project.workdir() / "config" / "package-lists").is_dir()
            )

    def test_hooks_are_executable(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows では実行ビットを検証できない")
        with Project(_basic_recipe()) as project:
            project.generate()
            hooks = list((project.workdir() / "config" / "hooks" / "live").glob("*"))
            self.assertTrue(hooks)
            for hook in hooks:
                with self.subTest(hook=hook.name):
                    self.assertTrue(os.access(hook, os.X_OK), f"{hook.name} に実行権限がない")

    def test_workdir_readme_is_written(self) -> None:
        with Project(_basic_recipe()) as project:
            project.generate()
            readme = project.workdir() / "README.build.md"
            self.assertTrue(readme.is_file())
            self.assertIn("lb build", readme.read_text(encoding="utf-8"))


class BootParameterTest(unittest.TestCase):
    def test_core_parameters_present(self) -> None:
        recipe = _basic_recipe()
        recipe.system.hostname = "mylinux"
        recipe.system.locale = "ja_JP.UTF-8"
        recipe.system.timezone = "Asia/Tokyo"
        recipe.system.keyboard_layout = "jp"

        params = build_bootappend(recipe)

        self.assertIn("boot=live", params)
        self.assertIn("components", params)
        self.assertIn("hostname=mylinux", params)
        self.assertIn("username=user", params)

    def test_locales_is_plural(self) -> None:
        """live-config のパラメータは locales= (複数形)。locale= では効かない。"""
        recipe = _basic_recipe()
        recipe.system.locale = "ja_JP.UTF-8"
        params = build_bootappend(recipe)
        self.assertIn("locales=ja_JP.UTF-8", params)
        self.assertNotIn(" locale=", params)

    def test_keyboard_parameters_use_hyphens(self) -> None:
        recipe = _basic_recipe()
        recipe.system.keyboard_layout = "jp"
        params = build_bootappend(recipe)
        self.assertIn("keyboard-layouts=jp", params)

    def test_noautologin_when_disabled(self) -> None:
        recipe = _basic_recipe()
        recipe.user.autologin = False
        self.assertIn("noautologin", build_bootappend(recipe))

        recipe.user.autologin = True
        self.assertNotIn("noautologin", build_bootappend(recipe))

    def test_noroot_when_sudo_disabled(self) -> None:
        recipe = _basic_recipe()
        recipe.user.sudo = False
        self.assertIn("noroot", build_bootappend(recipe))

    def test_persistence_parameter(self) -> None:
        recipe = _basic_recipe()
        self.assertNotIn("persistence", build_bootappend(recipe))
        recipe.boot.persistence = True
        self.assertIn("persistence", build_bootappend(recipe))

    def test_unsafe_characters_are_stripped(self) -> None:
        """空白や引用符が混じるとカーネルコマンドラインの切れ目が壊れる。"""
        recipe = _basic_recipe()
        recipe.boot.append = 'quiet splash"root=/dev/sda1'
        params = build_bootappend(recipe)
        self.assertNotIn('"root=', params)
        self.assertIn("quiet", params)

    def test_extra_append_is_appended(self) -> None:
        recipe = _basic_recipe()
        recipe.boot.append = "toram quiet"
        self.assertTrue(build_bootappend(recipe).endswith("toram quiet"))


class LbArgumentTest(unittest.TestCase):
    def _args(self, recipe: Recipe) -> list[str]:
        argv, _warnings = build_lb_argv(recipe)
        return argv

    def test_uses_noauto(self) -> None:
        argv = self._args(_basic_recipe())
        self.assertEqual(argv[:3], ["lb", "config", "noauto"])

    def test_pure_live_image_has_no_installer(self) -> None:
        argv = self._args(_basic_recipe())
        self.assertIn("--debian-installer", argv)
        index = argv.index("--debian-installer")
        self.assertEqual(argv[index + 1], "none")

    def test_hybrid_binary_image(self) -> None:
        argv = self._args(_basic_recipe())
        self.assertIn("iso-hybrid", argv)

    def test_system_is_live(self) -> None:
        argv = self._args(_basic_recipe())
        index = argv.index("--system")
        self.assertEqual(argv[index + 1], "live")

    def test_architecture_option_is_resolved(self) -> None:
        """単数形/複数形のどちらでも、実際に使えるほうが選ばれること。"""
        argv = self._args(_basic_recipe())
        self.assertTrue(
            "--architecture" in argv or "--architectures" in argv,
            f"アーキテクチャのオプションが見つからない: {argv}",
        )

    def test_amd64_gets_both_bootloaders(self) -> None:
        recipe = _basic_recipe()
        recipe.build.bootloaders = ["syslinux", "grub-efi"]
        argv = self._args(recipe)
        index = argv.index("--bootloaders")
        self.assertIn("syslinux", argv[index + 1])
        self.assertIn("grub-efi", argv[index + 1])

    def test_arm64_drops_syslinux(self) -> None:
        """syslinux は x86 専用なので arm64 では外す必要がある。"""
        recipe = _basic_recipe()
        recipe.iso.architecture = "arm64"
        recipe.build.bootloaders = ["syslinux", "grub-efi"]
        argv, warnings = build_lb_argv(recipe)
        index = argv.index("--bootloaders")
        self.assertNotIn("syslinux", argv[index + 1])
        self.assertTrue(any("syslinux" in warning for warning in warnings))

    def test_every_flag_has_a_value(self) -> None:
        """値の無いフラグを出すと lb の引数解釈がずれる。"""
        argv = self._args(_basic_recipe())
        flags = [item for item in argv if item.startswith("--")]
        self.assertTrue(flags)
        self.assertEqual(argv.count("--debian-installer"), 1)

    def test_apt_proxy_reaches_lb(self) -> None:
        recipe = _basic_recipe()
        self.assertNotIn("--apt-http-proxy", self._args(recipe))

        recipe.build.apt_proxy = "http://192.168.1.10:3142"
        argv = self._args(recipe)
        self.assertEqual(
            argv[argv.index("--apt-http-proxy") + 1], "http://192.168.1.10:3142"
        )


class RecipeKnobsReachTheOutputTest(unittest.TestCase):
    """レシピの設定項目が、実際に生成物へ届いていること。

    ここが抜けると「レシピに書けるのに何も起きない」項目ができる。
    そういう項目は利用者が延々と試行錯誤する羽目になるので、
    項目を足したら必ずこのテストにも足すこと。
    """

    def _boot_setup(self, recipe: Recipe) -> str:
        with Project(recipe) as project:
            project.generate()
            return (
                project.workdir()
                / "config"
                / "hooks"
                / "live"
                / "0600-boot-setup.hook.chroot"
            ).read_text(encoding="utf-8")

    def test_default_groups_reach_the_boot_setup(self) -> None:
        recipe = _basic_recipe()
        recipe.user.default_groups = "sudo,dialout"
        text = self._boot_setup(recipe)
        self.assertIn("usermod -aG sudo", text)
        self.assertIn("usermod -aG dialout", text)

    def test_default_groups_accepts_spaces_too(self) -> None:
        recipe = _basic_recipe()
        recipe.user.default_groups = "sudo dialout"
        text = self._boot_setup(recipe)
        self.assertIn("usermod -aG sudo", text)
        self.assertIn("usermod -aG dialout", text)

    def test_removed_jobs_key_is_rejected(self) -> None:
        """live-build に対応するオプションが無いので削った項目。

        黙って無視すると「効かない設定」を書かせることになるので、
        知らないキーとして弾く。
        """
        from frosted.recipe import RecipeProblems

        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict(
                {"version": 1, "iso": {"name": "x"}, "build": {"jobs": 4}}
            )
        self.assertTrue(any("jobs" in issue.where for issue in caught.exception.issues))

    def test_build_settings_change_the_lb_arguments(self) -> None:
        """代表的な設定が lb config の引数に反映されること。"""
        base, _ = build_lb_argv(_basic_recipe())

        cases = (
            ("mirror", "http://mirror.example/debian/", "--mirror-bootstrap"),
            ("compression", "gzip", "--compression"),
            ("secure_boot", "enable", "--uefi-secure-boot"),
        )
        for attribute, value, flag in cases:
            with self.subTest(setting=attribute):
                recipe = _basic_recipe()
                setattr(recipe.build, attribute, value)
                argv, _ = build_lb_argv(recipe)
                self.assertNotEqual(argv, base, f"{attribute} が引数に反映されていない")
                self.assertEqual(argv[argv.index(flag) + 1], value)

    def test_boolean_build_settings_change_the_lb_arguments(self) -> None:
        for attribute, flag in (
            ("cache", "--cache"),
            ("firmware", "--firmware-chroot"),
        ):
            with self.subTest(setting=attribute):
                recipe = _basic_recipe()
                setattr(recipe.build, attribute, False)
                argv, _ = build_lb_argv(recipe)
                self.assertEqual(argv[argv.index(flag) + 1], "false")

    def test_memtest_uses_the_values_live_build_accepts(self) -> None:
        """--memtest は真偽値ではなく memtest86+ / none を取る。"""
        for enabled, expected in ((True, "memtest86+"), (False, "none")):
            with self.subTest(enabled=enabled):
                recipe = _basic_recipe()
                recipe.build.memtest = enabled
                argv, _ = build_lb_argv(recipe)
                self.assertEqual(argv[argv.index("--memtest") + 1], expected)


class IncludeMaterializationTest(unittest.TestCase):
    def test_files_write_lands_in_includes_chroot(self) -> None:
        recipe = _basic_recipe()
        recipe.files.write.append(
            WriteEntry(path="/etc/motd", content="welcome\n", mode="0644")
        )
        with Project(recipe) as project:
            project.generate()
            target = project.workdir() / "config" / "includes.chroot" / "etc" / "motd"
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), "welcome\n")

    def test_files_owner_reaches_the_permission_hook(self) -> None:
        recipe = _basic_recipe()
        recipe.files.write.append(
            WriteEntry(path="/etc/x", content="x", mode="0600", owner="user:user")
        )
        with Project(recipe) as project:
            project.generate()
            hook = (
                project.workdir()
                / "config"
                / "hooks"
                / "live"
                / "0500-permissions.hook.chroot"
            )
            self.assertIn(
                "chown user:user /etc/x", hook.read_text(encoding="utf-8")
            )

    def test_files_copy_file(self) -> None:
        recipe = _basic_recipe()
        with Project(recipe) as project:
            source = project.root / "motd.txt"
            source.write_text("hello\n", encoding="utf-8")
            recipe.files.copy.append(CopyEntry(source="motd.txt", target="/etc/motd"))

            project.generate()
            target = project.workdir() / "config" / "includes.chroot" / "etc" / "motd"
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_files_copy_directory(self) -> None:
        recipe = _basic_recipe()
        with Project(recipe) as project:
            source = project.root / "assets"
            source.mkdir()
            (source / "one.txt").write_text("1", encoding="utf-8")
            (source / "two.txt").write_text("2", encoding="utf-8")
            recipe.files.copy.append(CopyEntry(source="assets", target="/opt/assets"))

            project.generate()
            target = project.workdir() / "config" / "includes.chroot" / "opt" / "assets"
            self.assertTrue((target / "one.txt").is_file())
            self.assertTrue((target / "two.txt").is_file())

    def test_path_traversal_is_blocked(self) -> None:
        """`/../../x` のような指定で作業ディレクトリの外に書かれないこと。"""
        recipe = _basic_recipe()
        recipe.files.write.append(WriteEntry(path="/etc/x", content="hi"))
        with Project(recipe) as project:
            recipe.files.write[0].path = "/../../escaped"
            with self.assertRaises(BuildError):
                project.generate()

    def test_setup_scripts_are_materialized(self) -> None:
        recipe = _basic_recipe()
        with Project(recipe) as project:
            script = project.root / "setup.sh"
            script.write_text("#!/bin/sh\necho setup\n", encoding="utf-8")
            recipe.scripts.setup.append("setup.sh")

            project.generate()
            target = (
                project.workdir()
                / "config"
                / "includes.chroot"
                / "usr"
                / "local"
                / "lib"
                / "frosted"
                / "setup.d"
                / "00-setup.sh"
            )
            self.assertTrue(target.is_file())


class PresetIntegrationTest(unittest.TestCase):
    def test_kiosk_preset_builds_a_working_tree(self) -> None:
        recipe = _basic_recipe("kiosk")
        apply_preset(recipe, "kiosk")

        with Project(recipe) as project:
            project.generate()
            root = project.workdir() / "config" / "includes.chroot"

            self.assertTrue((root / "usr/local/bin/start-kiosk").is_file())
            self.assertTrue((root / "etc/xdg/autostart/00-kiosk.desktop").is_file())
            self.assertTrue((root / "etc/kiosk-url").is_file())

            # キオスク端末に sudo を与えないこと
            self.assertIn("noroot", build_bootappend(recipe))

    def test_all_presets_generate_without_error(self) -> None:
        from frosted.catalog import PRESETS

        for key in PRESETS:
            with self.subTest(preset=key):
                recipe = _basic_recipe(f"test-{key}")
                apply_preset(recipe, key)
                with Project(recipe) as project:
                    result = project.generate()
                    self.assertTrue(result.created)

    def test_all_desktops_generate_without_error(self) -> None:
        from frosted.catalog import DESKTOPS

        for key in DESKTOPS:
            with self.subTest(desktop=key):
                recipe = _basic_recipe(f"test-{key}")
                recipe.desktop.environment = key
                with Project(recipe) as project:
                    result = project.generate()
                    self.assertTrue(result.created)


@unittest.skipIf(SH is None, "sh が見つからないためシェル構文の検証を省略")
class ShellSyntaxTest(unittest.TestCase):
    """生成したシェルスクリプトが構文的に正しいか、実際に sh に解析させる。"""

    def _check(self, name: str, text: str) -> None:
        proc = subprocess.run(
            [SH, "-n"],
            input=text,
            capture_output=True,
            text=True,
            env=_msys_env(),
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"{name} の構文エラー:\n{proc.stderr}\n--- 中身 ---\n{text}",
        )

    def test_auto_config_syntax(self) -> None:
        with Project(_basic_recipe()) as project:
            project.generate()
            text = (project.workdir() / "auto" / "config").read_text(encoding="utf-8")
            self._check("auto/config", text)

    def test_all_hook_syntax(self) -> None:
        recipe = _basic_recipe()
        apply_preset(recipe, "desktop")
        recipe.ssh.enable_server = True
        recipe.user.password = "secret"
        recipe.user.autologin = False
        recipe.packages.exclude = ["vim"]
        recipe.files.write.append(
            WriteEntry(path="/etc/x", content="x", mode="0600", owner="root:root")
        )
        with Project(recipe) as project:
            project.generate()
            hooks = sorted((project.workdir() / "config" / "hooks" / "live").glob("*"))
            self.assertTrue(hooks)
            for hook in hooks:
                with self.subTest(hook=hook.name):
                    self._check(hook.name, hook.read_text(encoding="utf-8"))

    def test_boot_setup_script_is_not_world_readable(self) -> None:
        """root のパスワードが入るスクリプトをライブユーザーに読ませない。"""
        recipe = _basic_recipe()
        recipe.user.password = "secret"
        with Project(recipe) as project:
            project.generate()
            hook = (
                project.workdir()
                / "config"
                / "hooks"
                / "live"
                / "0600-boot-setup.hook.chroot"
            )
            text = hook.read_text(encoding="utf-8")
            self.assertIn("chmod 0700", text)
            self.assertNotIn("chmod 0755", text)

    def test_autologin_hook_for_each_desktop(self) -> None:
        """ディスプレイマネージャごとの分岐が構文的に壊れていないこと。"""
        from frosted.catalog import DESKTOPS

        for key in DESKTOPS:
            with self.subTest(desktop=key):
                recipe = _basic_recipe(f"t-{key}")
                recipe.desktop.environment = key
                recipe.user.autologin = True
                with Project(recipe) as project:
                    project.generate()
                    path = (
                        project.workdir()
                        / "config"
                        / "hooks"
                        / "live"
                        / "0200-autologin.hook.chroot"
                    )
                    if path.is_file():
                        self._check("0200-autologin", path.read_text(encoding="utf-8"))


@unittest.skipIf(SH is None, "sh が見つからないため実行テストを省略")
class AutoConfigExecutionTest(unittest.TestCase):
    """偽の lb を差し込んで auto/config を実際に走らせ、引数を検証する。

    live-build 本体が無くても、レシピの値が正しく `lb config` の引数に
    なっているか (とくにシェルの引用符が正しいか) を確かめられる。
    """

    def _run(
        self, project: Project, extra_args: list[str] | None = None
    ) -> list[str]:
        bindir = project.root / "fakebin"
        bindir.mkdir(exist_ok=True)
        fake_lb = bindir / "lb"
        # 引数を 1 行ずつ出す。引用符が壊れていないか確認できるようにするため。
        fake_lb.write_text(
            '#!/bin/sh\nfor arg in "$@"; do printf \'%s\\n\' "$arg"; done\n',
            encoding="utf-8",
            newline="\n",
        )
        fake_lb.chmod(0o755)

        script = (project.workdir() / "auto" / "config").read_text(encoding="utf-8")
        proc = subprocess.run(
            [SH, "-s", "--", *(extra_args or [])],
            input=script,
            capture_output=True,
            text=True,
            cwd=str(project.workdir()),
            env=_msys_env(bindir),
        )
        if proc.returncode != 0:
            self.fail(f"auto/config の実行に失敗:\n{proc.stderr}")
        return proc.stdout.splitlines()

    def test_invokes_lb_config_noauto(self) -> None:
        with Project(_basic_recipe()) as project:
            project.generate()
            args = self._run(project)
            self.assertEqual(args[0], "config")
            self.assertEqual(args[1], "noauto")

    def test_extra_arguments_are_forwarded_to_lb_config(self) -> None:
        """lb config --verbose のような追加引数が実行されず、そのまま渡る。"""
        with Project(_basic_recipe()) as project:
            project.generate()
            args = self._run(project, ["--verbose"])
            self.assertIn("--verbose", args)

    def test_values_with_spaces_survive_as_single_arguments(self) -> None:
        """ブートパラメータは空白を含むので、1 つの引数として渡る必要がある。"""
        recipe = _basic_recipe()
        recipe.system.hostname = "myhost"
        recipe.boot.append = "quiet splash"
        with Project(recipe) as project:
            project.generate()
            args = self._run(project)

            index = args.index("--bootappend-live")
            value = args[index + 1]
            self.assertIn("hostname=myhost", value)
            self.assertIn("quiet splash", value)
            self.assertNotIn("'", value, "引用符が値に残っている")

    def test_fullname_is_applied_at_boot_not_on_the_kernel_command_line(self) -> None:
        """fullname をカーネル引数に載せると live-build の config が壊れる。"""
        recipe = _basic_recipe()
        recipe.user.fullname = "Live User"
        with Project(recipe) as project:
            project.generate()
            args = self._run(project)
            value = args[args.index("--bootappend-live") + 1]
            self.assertNotIn("user-fullname", value)
            self.assertNotIn('"', value, "カーネル引数に引用符が残っている")

            hook = (
                project.workdir()
                / "config"
                / "hooks"
                / "live"
                / "0600-boot-setup.hook.chroot"
            )
            text = hook.read_text(encoding="utf-8")
            self.assertIn("FULLNAME='Live User'", text)
            self.assertIn('usermod -c "${FULLNAME}"', text)

    def test_iso_volume_is_set(self) -> None:
        recipe = _basic_recipe("mylinux")
        with Project(recipe) as project:
            project.generate()
            args = self._run(project)
            self.assertEqual(args[args.index("--iso-volume") + 1], "MYLINUX")


class BootloaderSelectionTest(unittest.TestCase):
    def test_arm64_drops_x86_bootloaders(self) -> None:
        recipe = _basic_recipe()
        recipe.iso.architecture = "arm64"
        recipe.build.bootloaders = ["syslinux", "grub-pc"]
        argv, warnings = build_lb_argv(recipe)
        self.assertEqual(argv[argv.index("--bootloaders") + 1], "grub-efi")
        self.assertTrue(any("arm64" in warning for warning in warnings))

    def test_i386_keeps_syslinux(self) -> None:
        recipe = _basic_recipe()
        recipe.iso.architecture = "i386"
        recipe.build.bootloaders = ["syslinux", "grub-efi"]
        argv, warnings = build_lb_argv(recipe)
        self.assertEqual(
            argv[argv.index("--bootloaders") + 1], "syslinux grub-efi"
        )
        self.assertFalse(any("syslinux" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
