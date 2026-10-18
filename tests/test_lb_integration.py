"""live-build 本体と突き合わせる統合テスト。

ここだけは live-build がインストールされていないと走らない。開発機
(Windows) では省略され、Debian の CI と実機でだけ実行される。

確認したいのは 1 点に尽きる。**こちらが生成した auto/config を、本物の
live-build が受け付けるか。** `--architecture` と `--architectures` のような
綴りの揺れは実行時に解決する設計にしているが、その解決が正しく効いて
いるかを確かめられるのは実際の lb だけ。

`FROSTED_REQUIRE_LB=1` を付けると、lb が無いときに省略せず失敗する。
CI ではこれを付けて「lb の導入に失敗したのに緑になる」ことを防ぐ。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted.backend.livebuild import (  # noqa: E402
    OPTION_ALIASES,
    build_lb_args,
    generate,
    probe_option_spellings,
)
from frosted.catalog import DESKTOPS, PRESETS, apply_preset  # noqa: E402
from frosted.recipe import Recipe  # noqa: E402

LB = shutil.which("lb")
REQUIRE = os.environ.get("FROSTED_REQUIRE_LB") == "1"

#: lb config が長引いたときにテストが固まらないようにする
TIMEOUT = 300


@unittest.skipIf(LB is None and not REQUIRE, "live-build が入っていないため省略")
class LiveBuildOptionTest(unittest.TestCase):
    """生成するオプションが実際の lb config に存在すること。"""

    def setUp(self) -> None:
        if LB is None:
            self.fail(
                "FROSTED_REQUIRE_LB=1 が指定されていますが lb が見つかりません。"
                "live-build の導入に失敗しています。"
            )

    def test_lb_config_help_is_readable(self) -> None:
        spellings = probe_option_spellings(refresh=True)
        self.assertTrue(
            spellings.probed,
            "`lb config --help` からオプションを読み取れませんでした。"
            "live-build の出力形式が変わった可能性があります。",
        )

    def test_every_option_we_emit_is_supported(self) -> None:
        """レシピの全項目を埋めた状態で、落とされる設定が無いことを確認する。

        ここで警告が出るということは、その設定が黙って捨てられるということ。
        ビルドは通ってしまうので気づきにくい。
        """
        recipe = _fully_loaded_recipe()

        # 代表的な組み合わせを一通り試す
        for desktop in DESKTOPS:
            for preset in PRESETS:
                with self.subTest(desktop=desktop, preset=preset):
                    candidate = _fully_loaded_recipe()
                    candidate.desktop.environment = desktop
                    apply_preset(candidate, preset)

                    _args, warnings = build_lb_args(candidate)
                    self.assertEqual(
                        warnings,
                        [],
                        f"反映されない設定があります: {warnings}",
                    )

    def test_alias_candidates_are_all_real_options(self) -> None:
        """候補として書いた綴りが、少なくとも 1 つは実在すること。

        ここが空になると、その設定は永久に反映されない。
        """
        spellings = probe_option_spellings(refresh=True)

        # `lb config --help` を読む
        proc = subprocess.run(
            ["lb", "config", "--help"], capture_output=True, text=True, timeout=60
        )
        help_text = (proc.stdout or "") + (proc.stderr or "")

        missing = [
            key
            for key, aliases in OPTION_ALIASES.items()
            if not any(alias in help_text for alias in aliases)
        ]
        self.assertEqual(
            missing,
            [],
            f"この live-build に存在しないオプションがあります: {missing}",
        )
        # 念のため resolver 経由でも取れることを確認
        for key in OPTION_ALIASES:
            with self.subTest(key=key):
                self.assertIsNotNone(spellings.get(key), f"{key} の綴りが解決できない")


@unittest.skipIf(LB is None and not REQUIRE, "live-build が入っていないため省略")
class LbConfigAcceptanceTest(unittest.TestCase):
    """生成した設定ツリーを lb config に実際に食わせてみる。"""

    def _run_lb_config(self, recipe: Recipe) -> subprocess.CompletedProcess[str]:
        workdir = recipe.workdir()
        generate(recipe)
        return subprocess.run(
            ["lb", "config"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            errors="replace",
        )

    def _check(self, recipe: Recipe) -> None:
        proc = self._run_lb_config(recipe)
        self.assertEqual(
            proc.returncode,
            0,
            "lb config が生成した設定を受け付けませんでした。\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        )

    def test_minimal_recipe_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Recipe()
            recipe.path = Path(tmp) / "recipe.toml"
            recipe.build.workdir = "build"
            recipe.iso.name = "citest"
            self._check(recipe)

    def test_config_binary_is_sourceable(self) -> None:
        """config/binary は lb build が source する。

        bootappend に引用符が混じると、lb config は通るのに lb build が
        `User ...: not found` で落ちる。ここで実際に source して確認する。
        """
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Recipe()
            recipe.path = Path(tmp) / "recipe.toml"
            recipe.build.workdir = "build"
            recipe.iso.name = "ci-bootappend"
            recipe.user.fullname = "Live User"
            recipe.boot.append = "quiet splash"
            proc = self._run_lb_config(recipe)
            self.assertEqual(
                proc.returncode,
                0,
                f"lb config が失敗しました:\n{proc.stdout}\n{proc.stderr}",
            )

            config_file = recipe.workdir() / "config" / "binary"
            self.assertTrue(config_file.is_file())
            sourced = subprocess.run(
                ["sh", "-c", ". ./config/binary"],
                cwd=str(recipe.workdir()),
                capture_output=True,
                text=True,
                timeout=60,
                errors="replace",
            )
            self.assertEqual(
                sourced.returncode,
                0,
                "config/binary を source できません。\n"
                f"--- stderr ---\n{sourced.stderr}\n"
                f"--- config/binary ---\n{config_file.read_text(encoding='utf-8')}",
            )

    def test_memtest_recipe_is_accepted(self) -> None:
        """memtest 有効時は --memtest memtest86+ を出す必要がある。"""
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Recipe()
            recipe.path = Path(tmp) / "recipe.toml"
            recipe.build.workdir = "build"
            recipe.iso.name = "ci-memtest"
            recipe.build.memtest = True
            self._check(recipe)

    def test_each_preset_is_accepted(self) -> None:
        for preset in PRESETS:
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as tmp:
                recipe = Recipe()
                recipe.path = Path(tmp) / "recipe.toml"
                recipe.build.workdir = "build"
                recipe.iso.name = f"ci-{preset}"
                apply_preset(recipe, preset)
                self._check(recipe)

    def test_fully_loaded_recipe_is_accepted(self) -> None:
        """APT・インストーラー・カーネル設定を含む全項目を lb config に通す。"""
        with tempfile.TemporaryDirectory() as tmp:
            recipe = _fully_loaded_recipe()
            recipe.path = Path(tmp) / "recipe.toml"
            recipe.build.workdir = "build"
            recipe.iso.name = "ci-full"
            self._check(recipe)

    def test_rolling_distributions_are_accepted(self) -> None:
        for distribution in ("testing", "sid"):
            with self.subTest(distribution=distribution), tempfile.TemporaryDirectory() as tmp:
                recipe = Recipe()
                recipe.path = Path(tmp) / "recipe.toml"
                recipe.build.workdir = "build"
                recipe.iso.name = f"ci-{distribution}"
                recipe.iso.distribution = distribution
                self._check(recipe)

    def test_arm64_recipe_is_accepted(self) -> None:
        """アーキテクチャによってブートローダの選択が変わる部分の確認。"""
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Recipe()
            recipe.path = Path(tmp) / "recipe.toml"
            recipe.build.workdir = "build"
            recipe.iso.name = "ci-arm64"
            recipe.iso.architecture = "arm64"
            self._check(recipe)


def _fully_loaded_recipe() -> Recipe:
    """設定可能な項目をひととおり埋めたレシピ。

    検証したいのは「出すオプションが対応しているか」なので、
    実際には使わない項目も埋めておく。
    """
    recipe = Recipe()
    recipe.iso.name = "citest"
    recipe.iso.version = "1.0"
    recipe.iso.publisher = "Example Project"
    recipe.iso.preparer = "CI"
    recipe.system.hostname = "citest"
    recipe.system.locale = "ja_JP.UTF-8"
    recipe.system.timezone = "Asia/Tokyo"
    recipe.system.keyboard_layout = "jp"
    recipe.user.name = "tester"
    recipe.user.sudo = True
    recipe.user.autologin = True
    recipe.desktop.environment = "xfce"
    recipe.ssh.enable_server = True
    recipe.build.debootstrap_options = "--no-check-gpg"
    recipe.build.updates = False
    recipe.build.backports = False
    recipe.build.proposed_updates = False
    recipe.build.security = False
    recipe.build.source = False
    recipe.apt.backend = "apt"
    recipe.apt.secure = False
    recipe.apt.source_archives = False
    recipe.apt.indices = False
    recipe.apt.options = "--no-install-recommends"
    recipe.apt.pipeline = 1
    recipe.apt.keyring_packages = ["debian-archive-keyring"]
    recipe.apt.preferences = "Package: *\nPin: release a=trixie\nPin-Priority: 100"
    recipe.build.extra_repositories = [
        "deb https://repo.example.com/debian trixie main"
    ]
    recipe.build.repositories_in_image = True
    recipe.installer.type = "live"
    recipe.installer.gui = False
    recipe.installer.distribution = "trixie"
    recipe.kernel.packages = "linux-image"
    recipe.kernel.flavours = ["amd64"]
    recipe.boot.install_append = "quiet splash"
    recipe.binary.filesystem = "fat32"
    recipe.binary.chroot_filesystem = "squashfs"
    recipe.binary.squashfs_compression = "zstd"
    recipe.binary.squashfs_compression_level = 19
    recipe.binary.initramfs_compression = "gzip"
    recipe.binary.zsync = False
    recipe.binary.win32_loader = False
    recipe.binary.swap_file_path = "/swapfile"
    recipe.binary.swap_file_size = 256
    recipe.build.debconf_frontend = "noninteractive"
    recipe.build.debconf_priority = "critical"
    recipe.build.firmware_binary = True
    recipe.build.initsystem = "systemd"
    recipe.build.initramfs = "live-boot"
    return recipe


if __name__ == "__main__":
    unittest.main()
