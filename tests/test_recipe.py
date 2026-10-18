"""レシピの読み書きと検証のテスト。

Windows でも動くように標準ライブラリの unittest だけで書いている。
Debian 側に入れる前に、こちらで壊れていないことを確かめるのが目的。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted.recipe import (  # noqa: E402
    Recipe,
    RecipeProblems,
    WriteEntry,
    dumps,
)


class RecipeDefaultsTest(unittest.TestCase):
    def test_minimal_recipe_has_sensible_defaults(self) -> None:
        recipe = Recipe.from_dict({"version": 1, "iso": {"name": "mylinux"}})

        self.assertEqual(recipe.iso.name, "mylinux")
        self.assertEqual(recipe.iso.distribution, "trixie")
        self.assertEqual(recipe.iso.architecture, "amd64")
        self.assertEqual(recipe.user.name, "user")
        self.assertTrue(recipe.user.autologin)
        self.assertTrue(recipe.user.sudo)
        self.assertIn("non-free-firmware", recipe.build.archive_areas)
        self.assertEqual(recipe.build.workdir, "build")

    def test_name_is_required(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict({"version": 1})
        self.assertTrue(
            any(issue.where == "iso.name" for issue in caught.exception.issues)
        )

    def test_unknown_key_is_rejected(self) -> None:
        """打ち間違いを黙って無視すると原因が分からなくなるので、必ず弾く。"""
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict(
                {"version": 1, "iso": {"name": "mylinux", "versoin": "1.0"}}
            )
        message = caught.exception.issues[0].message
        self.assertIn("versoin", message)

    def test_unknown_section_is_rejected(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict({"version": 1, "iso": {"name": "x"}, "isoo": {}})
        self.assertTrue(any("isoo" in issue.where for issue in caught.exception.issues))

    def test_future_recipe_version_is_rejected(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict({"version": 99, "iso": {"name": "x"}})
        self.assertTrue(any(issue.where == "version" for issue in caught.exception.issues))


class RecipeValidationTest(unittest.TestCase):
    def _errors(self, data: dict) -> list[str]:
        try:
            Recipe.from_dict(data)
        except RecipeProblems as problems:
            return [issue.where for issue in problems.issues if issue.is_error]
        return []

    def test_bad_iso_name(self) -> None:
        self.assertIn("iso.name", self._errors({"version": 1, "iso": {"name": "My Linux"}}))
        self.assertIn("iso.name", self._errors({"version": 1, "iso": {"name": "-bad"}}))
        self.assertIn("iso.name", self._errors({"version": 1, "iso": {"name": "bad-"}}))

    def test_good_iso_names(self) -> None:
        for name in ("a", "mylinux", "my-linux-1", "x1"):
            with self.subTest(name=name):
                self.assertEqual(self._errors({"version": 1, "iso": {"name": name}}), [])

    def test_bad_architecture(self) -> None:
        self.assertIn(
            "iso.architecture",
            self._errors({"version": 1, "iso": {"name": "x", "architecture": "sparc"}}),
        )

    def test_unknown_distribution_is_only_a_warning(self) -> None:
        recipe = Recipe.from_dict(
            {"version": 1, "iso": {"name": "x", "distribution": "forky"}}
        )
        self.assertTrue(
            any(issue.where == "iso.distribution" for issue in recipe.warnings)
        )

    def test_bad_locale(self) -> None:
        self.assertIn(
            "system.locale",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "system": {"locale": "日本語"}}
            ),
        )

    def test_accepted_locales(self) -> None:
        """C.UTF-8 は言語コードではないが実際によく使うので通す必要がある。"""
        for locale in (
            "C.UTF-8",
            "C",
            "POSIX",
            "ja_JP.UTF-8",
            "en_US.UTF-8",
            "de_DE.UTF-8@euro",
            "en_GB",
        ):
            with self.subTest(locale=locale):
                self.assertNotIn(
                    "system.locale",
                    self._errors(
                        {"version": 1, "iso": {"name": "x"}, "system": {"locale": locale}}
                    ),
                )

    def test_username_rules(self) -> None:
        for name in ("Root", "1abc", "with space", "root"):
            with self.subTest(name=name):
                self.assertIn(
                    "user.name",
                    self._errors({"version": 1, "iso": {"name": "x"}, "user": {"name": name}}),
                )

    def test_password_with_colon_is_rejected(self) -> None:
        """chpasswd は 1 行で読むので、コロンが混じると別のユーザーとして解釈される。"""
        self.assertIn(
            "user.password",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "user": {"password": "a:b"}}
            ),
        )

    def test_fullname_with_quote_is_accepted(self) -> None:
        """fullname は起動後に設定するので、引用符は shlex.quote で守れる。"""
        name = 'O\'Brien "Bob"'
        recipe = Recipe.from_dict(
            {"version": 1, "iso": {"name": "x"}, "user": {"fullname": name}}
        )
        self.assertEqual(recipe.user.fullname, name)
        self.assertFalse(
            any(issue.where == "user.fullname" for issue in recipe.warnings)
        )

    def test_fullname_with_colon_is_rejected(self) -> None:
        """コロンは /etc/passwd の GECOS 区切りなので拒否する。"""
        self.assertIn(
            "user.fullname",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "user": {"fullname": "Bad:Name"}}
            ),
        )

    def test_missing_wallpaper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = {
                "version": 1,
                "iso": {"name": "x"},
                "desktop": {"wallpaper": str(Path(tmp) / "missing.png")},
            }
            self.assertIn("desktop.wallpaper", self._errors(data))

    def test_wallpaper_without_desktop_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "wall.png"
            image.write_bytes(b"png")
            recipe = Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "desktop": {"environment": "none", "wallpaper": str(image)},
                }
            )
        self.assertTrue(
            any(
                issue.where == "desktop.wallpaper"
                for issue in recipe.warnings
            )
        )

    def test_bad_apt_backend_is_rejected(self) -> None:
        self.assertIn(
            "apt.backend",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "apt": {"backend": "yum"},
                }
            ),
        )

    def test_bad_installer_type_is_rejected(self) -> None:
        self.assertIn(
            "installer.type",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "installer": {"type": "floppy"},
                }
            ),
        )

    def test_missing_preseed_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn(
                "installer.preseed",
                self._errors(
                    {
                        "version": 1,
                        "iso": {"name": "x"},
                        "installer": {
                            "type": "live",
                            "preseed": str(Path(tmp) / "missing.cfg"),
                        },
                    }
                ),
            )

    def test_bad_binary_image_type_is_rejected(self) -> None:
        self.assertIn(
            "binary.image_type",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"image_type": "floppy"},
                }
            ),
        )

    def test_bad_debconf_frontend_is_rejected(self) -> None:
        self.assertIn(
            "build.debconf_frontend",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "build": {"debconf_frontend": "gui"},
                }
            ),
        )

    def test_bad_initsystem_and_initramfs_are_rejected(self) -> None:
        for key, value in (
            ("initsystem", "upstart"),
            ("initramfs", "dracut"),
        ):
            with self.subTest(key=key):
                self.assertIn(
                    f"build.{key}",
                    self._errors(
                        {
                            "version": 1,
                            "iso": {"name": "x"},
                            "build": {key: value},
                        }
                    ),
                )

    def test_swap_file_requires_absolute_path(self) -> None:
        self.assertIn(
            "binary.swap_file_path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"swap_file_path": "swapfile"},
                }
            ),
        )
        self.assertIn(
            "binary.swap_file_path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"swap_file_path": "/tmp/../swapfile"},
                }
            ),
        )
        self.assertIn(
            "binary.swap_file_path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"swap_file_path": "/swap/"},
                }
            ),
        )
        self.assertIn(
            "binary.swap_file_path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"swap_file_path": "/"},
                }
            ),
        )
        self.assertIn(
            "binary.swap_file_size",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "binary": {"swap_file_path": "/swapfile", "swap_file_size": 0},
                }
            ),
        )

    def test_swap_size_without_path_is_a_warning(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "binary": {"swap_file_size": 1024},
            }
        )
        self.assertTrue(
            any(issue.where == "binary.swap_file_size" for issue in recipe.warnings)
        )

    def test_boot_install_append_rejects_quotes(self) -> None:
        self.assertIn(
            "boot.install_append",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "boot": {"install_append": 'quiet "oops"'},
                }
            ),
        )

    def test_local_package_with_wrong_suffix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / "hello_1.0_noarch.deb"
            deb.write_bytes(b"deb")
            self.assertIn(
                "packages.local",
                self._errors(
                    {
                        "version": 1,
                        "iso": {"name": "x"},
                        "packages": {"local": [str(deb)]},
                    }
                ),
            )

    def test_local_package_for_another_architecture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / "hello_1.0_i386.deb"
            deb.write_bytes(b"deb")
            self.assertIn(
                "packages.local",
                self._errors(
                    {
                        "version": 1,
                        "iso": {"name": "x", "architecture": "amd64"},
                        "packages": {"local": [str(deb)]},
                    }
                ),
            )

    def test_duplicate_local_package_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "one"
            two = Path(tmp) / "two"
            one.mkdir()
            two.mkdir()
            for directory in (one, two):
                (directory / "hello_1.0_amd64.deb").write_bytes(b"deb")
            self.assertIn(
                "packages.local",
                self._errors(
                    {
                        "version": 1,
                        "iso": {"name": "x"},
                        "packages": {
                            "local": [
                                str(one / "hello_1.0_amd64.deb"),
                                str(two / "hello_1.0_amd64.deb"),
                            ]
                        },
                    }
                ),
            )

    def test_missing_local_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn(
                "packages.local",
                self._errors(
                    {
                        "version": 1,
                        "iso": {"name": "x"},
                        "packages": {
                            "local": [str(Path(tmp) / "missing_1.0_amd64.deb")]
                        },
                    }
                ),
            )

    def test_bad_kernel_flavour_is_rejected(self) -> None:
        self.assertIn(
            "kernel.flavours",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "kernel": {"flavours": ["bad flavour"]},
                }
            ),
        )

    def test_missing_repository_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = {
                "version": 1,
                "iso": {"name": "x"},
                "build": {
                    "repository_keys": [str(Path(tmp) / "missing.gpg")]
                },
            }
            self.assertIn("build.repository_keys", self._errors(data))

    def test_package_name_validation(self) -> None:
        self.assertIn(
            "packages.include",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "packages": {"include": ["Good-Pkg", "bad pkg"]},
                }
            ),
        )

    def test_absolute_path_required_for_files(self) -> None:
        self.assertIn(
            "files.write[0].path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "files": {"write": [{"path": "etc/motd", "content": "hi"}]},
                }
            ),
        )

    def test_path_traversal_is_rejected(self) -> None:
        self.assertIn(
            "files.write[0].path",
            self._errors(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "files": {"write": [{"path": "/etc/../../x", "content": "hi"}]},
                }
            ),
        )

    def test_bad_compression(self) -> None:
        self.assertIn(
            "build.compression",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "build": {"compression": "lzma"}}
            ),
        )

    def test_bad_mirror(self) -> None:
        self.assertIn(
            "build.mirror",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "build": {"mirror": "deb.debian.org"}}
            ),
        )

    def test_unknown_desktop(self) -> None:
        self.assertIn(
            "desktop.environment",
            self._errors(
                {"version": 1, "iso": {"name": "x"}, "desktop": {"environment": "unity"}}
            ),
        )

    def test_autologin_without_password_warns(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "user": {"autologin": False, "password": ""},
            }
        )
        self.assertTrue(any(issue.where == "user.password" for issue in recipe.warnings))

    def test_missing_script_file_is_an_error(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "scripts": {"setup": ["/nonexistent/setup.sh"]},
                }
            )
        self.assertTrue(
            any(issue.where == "scripts.setup" for issue in caught.exception.issues)
        )


class TomlRoundTripTest(unittest.TestCase):
    def _roundtrip(self, recipe: Recipe) -> Recipe:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recipe.toml"
            recipe.save(path)
            return Recipe.load(path)

    def test_simple_roundtrip(self) -> None:
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "mylinux", "version": "2.0", "distribution": "bookworm"},
                "system": {"locale": "ja_JP.UTF-8", "timezone": "Asia/Tokyo"},
                "packages": {"include": ["vim", "curl"]},
            }
        )
        loaded = self._roundtrip(original)

        self.assertEqual(loaded.iso.name, original.iso.name)
        self.assertEqual(loaded.iso.version, original.iso.version)
        self.assertEqual(loaded.iso.distribution, original.iso.distribution)
        self.assertEqual(loaded.system.locale, original.system.locale)
        self.assertEqual(loaded.system.timezone, original.system.timezone)
        self.assertEqual(loaded.packages.include, original.packages.include)

    def test_multiline_content_roundtrip(self) -> None:
        """files.write の中身はシェルスクリプトなど改行を含むことが多い。"""
        content = "#!/bin/sh\nset -e\necho \"hello\"\n\nexit 0\n"
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {
                    "write": [{"path": "/usr/local/bin/hello", "content": content}]
                },
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.files.write[0].content, content)

    def test_content_with_quotes_and_backslashes(self) -> None:
        """引用符やバックスラッシュ、制御文字が壊れないこと。"""
        content = "a \"quoted\" value\nback\\slash\n\ttab\n'apostrophe'\n"
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {"write": [{"path": "/etc/x", "content": content}]},
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.files.write[0].content, content)

    def test_content_containing_triple_quote(self) -> None:
        """リテラル複数行文字列が使えない場合は別の書き方に落ちること。"""
        content = "before\n'''\nafter\n"
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {"write": [{"path": "/etc/x", "content": content}]},
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.files.write[0].content, content)

    def test_content_starting_with_newline(self) -> None:
        """TOML は開きデリミタ直後の改行を読み飛ばすので、そこがずれないこと。"""
        content = "\nleading newline\n"
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {"write": [{"path": "/etc/x", "content": content}]},
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.files.write[0].content, content)

    def test_empty_content_roundtrip(self) -> None:
        """空ファイルを作る指定が、保存・再読込で消えないこと。"""
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {"write": [{"path": "/etc/empty", "content": ""}]},
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.files.write[0].content, "")

    def test_empty_version_roundtrip(self) -> None:
        """空の version は出力名から省く指定なので、既定値に戻さない。"""
        original = Recipe.from_dict(
            {"version": 1, "iso": {"name": "x", "version": ""}}
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.iso.version, "")
        self.assertEqual(loaded.iso.resolved_output(), "x-amd64.iso")

    def test_empty_fullname_roundtrip(self) -> None:
        original = Recipe.from_dict(
            {"version": 1, "iso": {"name": "x"}, "user": {"fullname": ""}}
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.user.fullname, "")

    def test_apt_installer_kernel_roundtrip(self) -> None:
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "apt": {
                    "backend": "apt-get",
                    "secure": False,
                    "source_archives": False,
                    "indices": True,
                    "options": "--no-install-recommends",
                    "pipeline": 2,
                    "keyring_packages": ["debian-archive-keyring"],
                    "preferences": (
                        "Package: *\nPin: release a=trixie\nPin-Priority: 100"
                    ),
                },
                "installer": {
                    "type": "live",
                    "gui": False,
                    "distribution": "trixie",
                },
                "kernel": {
                    "packages": "linux-image",
                    "flavours": ["amd64"],
                },
                "boot": {
                    "install_append": "quiet splash",
                },
                "build": {
                    "firmware_binary": True,
                    "initsystem": "sysvinit",
                    "initramfs": "none",
                    "extra_repositories": [
                        "deb https://repo.example.com/debian trixie main"
                    ],
                    "repositories_in_image": True,
                },
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.apt.backend, "apt-get")
        self.assertFalse(loaded.apt.secure)
        self.assertEqual(loaded.apt.pipeline, 2)
        self.assertEqual(loaded.apt.keyring_packages, ["debian-archive-keyring"])
        self.assertIn("Pin-Priority: 100", loaded.apt.preferences)
        self.assertEqual(loaded.installer.type, "live")
        self.assertFalse(loaded.installer.gui)
        self.assertEqual(loaded.installer.distribution, "trixie")
        self.assertEqual(loaded.kernel.packages, "linux-image")
        self.assertEqual(loaded.kernel.flavours, ["amd64"])
        self.assertEqual(loaded.boot.install_append, "quiet splash")
        self.assertTrue(loaded.build.firmware_binary)
        self.assertEqual(loaded.build.initsystem, "sysvinit")
        self.assertEqual(loaded.build.initramfs, "none")
        self.assertEqual(
            loaded.build.extra_repositories,
            ["deb https://repo.example.com/debian trixie main"],
        )
        self.assertTrue(loaded.build.repositories_in_image)

    def test_binary_roundtrip(self) -> None:
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "binary": {
                    "image_type": "hdd",
                    "filesystem": "ext4",
                    "checksums": "sha512",
                    "chroot_filesystem": "squashfs",
                    "squashfs_compression": "zstd",
                    "squashfs_compression_level": 15,
                    "initramfs_compression": "lzma",
                    "zsync": True,
                    "win32_loader": False,
                    "swap_file_path": "/swapfile",
                    "swap_file_size": 1024,
                },
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.binary.image_type, "hdd")
        self.assertEqual(loaded.binary.filesystem, "ext4")
        self.assertEqual(loaded.binary.checksums, "sha512")
        self.assertEqual(loaded.binary.squashfs_compression, "zstd")
        self.assertEqual(loaded.binary.squashfs_compression_level, 15)
        self.assertEqual(loaded.binary.initramfs_compression, "lzma")
        self.assertTrue(loaded.binary.zsync)
        self.assertFalse(loaded.binary.win32_loader)
        self.assertEqual(loaded.binary.swap_file_path, "/swapfile")
        self.assertEqual(loaded.binary.swap_file_size, 1024)

    def test_local_package_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deb = Path(tmp) / "hello_1.0_amd64.deb"
            deb.write_bytes(b"deb")
            original = Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "packages": {"local": [str(deb)]},
                }
            )
            loaded = self._roundtrip(original)
        self.assertEqual(loaded.packages.local, [str(deb)])

    def test_wallpaper_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "wall.png"
            image.write_bytes(b"png")
            original = Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "desktop": {
                        "environment": "xfce",
                        "wallpaper": str(image),
                    },
                }
            )
            loaded = self._roundtrip(original)
        self.assertEqual(loaded.desktop.wallpaper, str(image))

    def test_repository_key_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "myrepo.gpg"
            key.write_bytes(b"key")
            original = Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "build": {"repository_keys": [str(key)]},
                }
            )
            loaded = self._roundtrip(original)
        self.assertEqual(loaded.build.repository_keys, [str(key)])

    def test_password_hash_roundtrip(self) -> None:
        """$ を含むハッシュもそのまま往復すること。"""
        hashed = "$6$rounds=5000$abcdef$ghijklmnop"
        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "user": {"password": hashed, "autologin": False},
            }
        )
        loaded = self._roundtrip(original)
        self.assertEqual(loaded.user.password, hashed)
        self.assertTrue(loaded.user.password_is_hashed())

    def test_dumps_is_parseable_by_tomllib(self) -> None:
        import tomllib

        recipe = Recipe()
        recipe.iso.name = "roundtrip"
        recipe.files.write.append(
            WriteEntry(path="/etc/x", content="line1\nline2\n", mode="0600")
        )
        text = dumps(recipe.to_dict())
        parsed = tomllib.loads(text)
        self.assertEqual(parsed["iso"]["name"], "roundtrip")
        self.assertEqual(parsed["files"]["write"][0]["content"], "line1\nline2\n")
        self.assertEqual(parsed["files"]["write"][0]["mode"], "0600")

    def test_files_owner_roundtrips_under_the_new_key(self) -> None:
        import tomllib

        original = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {
                    "write": [
                        {
                            "path": "/etc/x",
                            "content": "x",
                            "owner": "user:user",
                        }
                    ]
                },
            }
        )
        self.assertEqual(original.files.write[0].owner, "user:user")

        parsed = tomllib.loads(dumps(original.to_dict()))
        entry = parsed["files"]["write"][0]
        self.assertEqual(entry["owner"], "user:user")
        self.assertNotIn("Keychrom", entry)

    def test_legacy_keychrom_is_accepted_with_a_warning(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x"},
                "files": {
                    "write": [
                        {
                            "path": "/etc/x",
                            "content": "x",
                            "Keychrom": "user:user",
                        }
                    ]
                },
            }
        )
        self.assertEqual(recipe.files.write[0].owner, "user:user")
        self.assertTrue(
            any("Keychrom" in issue.where for issue in recipe.warnings),
            "旧名を使ったことを警告していない",
        )

    def test_owner_and_keychrom_together_are_rejected(self) -> None:
        with self.assertRaises(RecipeProblems):
            Recipe.from_dict(
                {
                    "version": 1,
                    "iso": {"name": "x"},
                    "files": {
                        "write": [
                            {
                                "path": "/etc/x",
                                "content": "x",
                                "owner": "user:user",
                                "Keychrom": "root:root",
                            }
                        ]
                    },
                }
            )

    def test_load_accepts_utf8_bom(self) -> None:
        """Windows のエディタが付ける BOM を構文エラーにしない。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recipe.toml"
            path.write_bytes(
                b'\xef\xbb\xbfversion = 1\n[iso]\nname = "bomtest"\n'
            )
            recipe = Recipe.load(path)
        self.assertEqual(recipe.iso.name, "bomtest")

    def test_bad_version_is_rejected(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict(
                {"version": 1, "iso": {"name": "x", "version": "1/2"}}
            )
        self.assertTrue(
            any(issue.where == "iso.version" for issue in caught.exception.issues)
        )

    def test_empty_workdir_is_rejected(self) -> None:
        with self.assertRaises(RecipeProblems) as caught:
            Recipe.from_dict(
                {"version": 1, "iso": {"name": "x"}, "build": {"workdir": ""}}
            )
        self.assertTrue(
            any(
                issue.where == "build.workdir"
                for issue in caught.exception.issues
            )
        )

    def test_rolling_distributions_are_accepted_with_a_warning(self) -> None:
        for distribution in ("testing", "forky", "sid", "unstable"):
            with self.subTest(distribution=distribution):
                recipe = Recipe.from_dict(
                    {
                        "version": 1,
                        "iso": {"name": "x", "distribution": distribution},
                    }
                )
                self.assertTrue(recipe.iso.is_rolling())
                self.assertTrue(
                    any(
                        issue.where == "iso.distribution"
                        for issue in recipe.warnings
                    )
                )

    def test_sid_ignores_the_security_mirror(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x", "distribution": "sid"},
                "build": {
                    "security_mirror": "http://security.debian.org/debian-security/"
                },
            }
        )
        self.assertFalse(recipe.iso.has_security_archive())
        self.assertTrue(
            any(
                issue.where == "build.security_mirror"
                for issue in recipe.warnings
            )
        )

    def test_i386_does_not_warn_about_syslinux(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x", "architecture": "i386"},
                "build": {"bootloaders": ["syslinux", "grub-efi"]},
            }
        )
        self.assertFalse(
            any(issue.where == "build.bootloaders" for issue in recipe.warnings)
        )

    def test_arm64_warns_about_x86_bootloaders(self) -> None:
        recipe = Recipe.from_dict(
            {
                "version": 1,
                "iso": {"name": "x", "architecture": "arm64"},
                "build": {"bootloaders": ["syslinux", "grub-efi"]},
            }
        )
        self.assertTrue(
            any(issue.where == "build.bootloaders" for issue in recipe.warnings)
        )


class DerivedValueTest(unittest.TestCase):
    def test_resolved_label_from_name(self) -> None:
        recipe = Recipe()
        recipe.iso.name = "my-linux-1"
        self.assertEqual(recipe.iso.resolved_label(), "MY_LINUX_1")

    def test_resolved_label_is_truncated_to_32_chars(self) -> None:
        """ISO のボリュームラベルは 32 文字までという制約がある。"""
        recipe = Recipe()
        recipe.iso.name = "a" * 40
        self.assertEqual(len(recipe.iso.resolved_label()), 32)

    def test_resolved_output_includes_version_and_arch(self) -> None:
        recipe = Recipe()
        recipe.iso.name = "mylinux"
        recipe.iso.version = "1.0"
        recipe.iso.architecture = "amd64"
        self.assertEqual(recipe.iso.resolved_output(), "mylinux-1.0-amd64.iso")

    def test_explicit_output_wins(self) -> None:
        recipe = Recipe()
        recipe.iso.name = "mylinux"
        recipe.iso.output = "custom.iso"
        self.assertEqual(recipe.iso.resolved_output(), "custom.iso")


if __name__ == "__main__":
    unittest.main()
