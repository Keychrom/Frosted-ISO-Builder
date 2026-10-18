"""公開用のリリース成果物のテスト。

配布物の検証は「壊れたものを受け取った人が気づけないと意味がない」ので、
チェックサムの形式と、改ざんを検出できることを重点的に見る。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted import release  # noqa: E402
from frosted.recipe import Recipe  # noqa: E402


class Sha256Test(unittest.TestCase):
    #: SHA-256 の標準的なテスト値。実装が正しいことを外部の既知値で確かめる。
    KNOWN = {
        b"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        b"abc": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }

    def test_matches_known_digests(self) -> None:
        for payload, expected in self.KNOWN.items():
            with self.subTest(payload=payload):
                self.assertEqual(release.sha256_bytes(payload), expected)

    def test_file_digest_matches_known_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.bin"
            path.write_bytes(b"abc")
            self.assertEqual(release.sha256_file(path), self.KNOWN[b"abc"])

    def test_handles_files_larger_than_the_read_chunk(self) -> None:
        """読み込み単位をまたぐ大きさでも一度に読んだ場合と一致すること。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.bin"
            payload = b"a" * (2 * 1024 * 1024 + 7)
            path.write_bytes(payload)
            self.assertEqual(release.sha256_file(path), release.sha256_bytes(payload))


class ChecksumFileTest(unittest.TestCase):
    def _iso(self, tmp: str, name: str = "test-1.0-amd64.iso", size: int = 4096) -> Path:
        path = Path(tmp) / name
        path.write_bytes(b"x" * size)
        return path

    def test_writes_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = self._iso(tmp)
            digest = release.sha256_file(iso)
            created = release.write_checksums(iso, digest)

            names = sorted(path.name for path in created)
            self.assertEqual(names, ["SHA256SUMS", "test-1.0-amd64.iso.sha256"])

            single = iso.with_name(f"{iso.name}.sha256")
            # sha256sum -c が読める形式 (ハッシュ + 2 スペース + ファイル名)
            self.assertEqual(single.read_text(encoding="utf-8"), f"{digest}  {iso.name}\n")

    def test_updates_only_the_matching_line(self) -> None:
        """同じディレクトリに複数の ISO があるとき、他の行を壊さないこと。"""
        with tempfile.TemporaryDirectory() as tmp:
            first = self._iso(tmp, "alpha-1.0-amd64.iso")
            second = self._iso(tmp, "beta-1.0-amd64.iso")

            release.write_checksums(first, release.sha256_file(first))
            release.write_checksums(second, release.sha256_file(second))

            sums = Path(tmp) / "SHA256SUMS"
            text = sums.read_text(encoding="utf-8")
            self.assertIn(first.name, text)
            self.assertIn(second.name, text)
            self.assertEqual(len([ln for ln in text.splitlines() if ln.strip()]), 2)

    def test_replaces_a_binary_marker_line(self) -> None:
        """sha256sum -b の `*name` 行も同じ ISO の行として置き換える。"""
        with tempfile.TemporaryDirectory() as tmp:
            iso = self._iso(tmp)
            sums = Path(tmp) / "SHA256SUMS"
            sums.write_text(f"{'a' * 64} *{iso.name}\n", encoding="utf-8")

            release.write_checksums(iso, "b" * 64)

            lines = [
                line
                for line in sums.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), 1)
            self.assertIn("b" * 64, lines[0])

    def test_rewriting_replaces_not_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = self._iso(tmp)
            release.write_checksums(iso, "a" * 64)
            release.write_checksums(iso, "b" * 64)

            text = (Path(tmp) / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(len([ln for ln in text.splitlines() if ln.strip()]), 1)
            self.assertIn("b" * 64, text)

    def test_no_carriage_returns(self) -> None:
        """Windows で作っても CR が混じらないこと (sha256sum が読めなくなる)。"""
        with tempfile.TemporaryDirectory() as tmp:
            iso = self._iso(tmp)
            release.write_checksums(iso, "c" * 64)
            for name in ("SHA256SUMS", f"{iso.name}.sha256"):
                with self.subTest(name=name):
                    self.assertNotIn(b"\r", (Path(tmp) / name).read_bytes())


class StaleArtifactTest(unittest.TestCase):
    def test_produce_removes_artifacts_from_the_previous_build(self) -> None:
        """--no-checksum や署名失敗で古い成果物を残さない。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso = root / "demo.iso"
            iso.write_bytes(b"new iso")

            stale = [
                root / "demo.iso.sha256",
                root / "demo.iso.build-info.json",
                root / "demo.iso.asc",
            ]
            for path in stale:
                path.write_text("stale\n", encoding="utf-8")
            sums = root / "SHA256SUMS"
            sums.write_text(
                f"{'a' * 64}  demo.iso\n{'b' * 64}  other.iso\n",
                encoding="utf-8",
            )

            release.produce(
                recipe=Recipe(),
                iso_path=iso,
                workdir=root / "build",
                bootappend="",
                lb_args=[],
                checksums=False,
                build_info=False,
            )

            for path in stale:
                with self.subTest(path=path.name):
                    self.assertFalse(path.exists())
            text = sums.read_text(encoding="utf-8")
            self.assertNotIn("demo.iso", text)
            self.assertIn("other.iso", text)


class DigestLookupTest(unittest.TestCase):
    """verify 側の照合ロジック。"""

    def _sums(self, tmp: str, text: str) -> Path:
        path = Path(tmp) / "SHA256SUMS"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def test_finds_the_matching_line(self) -> None:
        from frosted.cli import _expected_digest

        with tempfile.TemporaryDirectory() as tmp:
            sums = self._sums(
                tmp,
                f"{'a' * 64}  other.iso\n{'b' * 64}  target.iso\n",
            )
            self.assertEqual(_expected_digest(sums, "target.iso"), "b" * 64)

    def test_uppercase_digest_is_normalized(self) -> None:
        from frosted.cli import _expected_digest

        with tempfile.TemporaryDirectory() as tmp:
            sums = self._sums(tmp, f"{'A' * 64}  target.iso\n")
            self.assertEqual(_expected_digest(sums, "target.iso"), "a" * 64)

    def test_binary_marker_is_accepted(self) -> None:
        """sha256sum -b が付ける * 付きの行も読めること。"""
        from frosted.cli import _expected_digest

        with tempfile.TemporaryDirectory() as tmp:
            sums = self._sums(tmp, f"{'d' * 64} *target.iso\n")
            self.assertEqual(_expected_digest(sums, "target.iso"), "d" * 64)

    def test_single_line_file_falls_back(self) -> None:
        from frosted.cli import _expected_digest

        with tempfile.TemporaryDirectory() as tmp:
            sums = self._sums(tmp, f"{'e' * 64}  renamed.iso\n")
            self.assertEqual(_expected_digest(sums, "target.iso"), "e" * 64)

    def test_unknown_file_returns_none(self) -> None:
        from frosted.cli import _expected_digest

        with tempfile.TemporaryDirectory() as tmp:
            sums = self._sums(
                tmp, f"{'a' * 64}  one.iso\n{'b' * 64}  two.iso\n"
            )
            self.assertIsNone(_expected_digest(sums, "missing.iso"))


class VerifyCommandTest(unittest.TestCase):
    """verify は「検証していないのに成功」と言ってはいけない。"""

    ISO_BYTES = b"fake iso"

    def _run(
        self,
        tmp: str,
        sums_text: str | None,
        *,
        signature: bool = False,
        build_info_text: str | None = None,
    ) -> tuple[int, str]:
        import argparse
        import contextlib
        import io

        from frosted import cli

        iso = Path(tmp) / "image.iso"
        iso.write_bytes(self.ISO_BYTES)
        if sums_text is not None:
            (Path(tmp) / "image.iso.sha256").write_text(
                sums_text, encoding="utf-8", newline="\n"
            )
        if signature:
            (Path(tmp) / "image.iso.asc").write_text(
                "-----BEGIN PGP SIGNATURE-----\n", encoding="utf-8"
            )
        if build_info_text is not None:
            (Path(tmp) / "image.iso.build-info.json").write_text(
                build_info_text, encoding="utf-8"
            )

        args = argparse.Namespace(
            iso=str(iso), sums=None, signature=None, verbose=False
        )
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_verify(args)
        return code, out.getvalue() + err.getvalue()

    def test_matching_checksum_succeeds(self) -> None:
        digest = release.sha256_bytes(self.ISO_BYTES)
        with tempfile.TemporaryDirectory() as tmp:
            code, _text = self._run(tmp, f"{digest}  image.iso\n")
        self.assertEqual(code, 0)

    def test_mismatched_checksum_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _text = self._run(tmp, f"{'0' * 64}  image.iso\n")
        self.assertEqual(code, 1)

    def test_checksum_file_without_this_iso_fails(self) -> None:
        """該当行が無いだけなのに成功扱いになっていた回帰テスト。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _text = self._run(
                tmp,
                f"{'0' * 64}  other.iso\n{'1' * 64}  another.iso\n",
            )
        self.assertEqual(code, 1)

    def test_nothing_to_verify_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _text = self._run(tmp, None)
        self.assertEqual(code, 1)

    def test_malformed_build_info_does_not_crash(self) -> None:
        """配布物の build-info.json が壊れていても検証自体は続ける。"""
        digest = release.sha256_bytes(self.ISO_BYTES)
        with tempfile.TemporaryDirectory() as tmp:
            code, _text = self._run(
                tmp,
                f"{digest}  image.iso\n",
                build_info_text="[]\n",
            )
        self.assertEqual(code, 0)

    def test_signature_without_gpg_is_not_a_success(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(release, "gpg_available", return_value=False):
                code, _text = self._run(tmp, None, signature=True)
        self.assertEqual(code, 1)

    def test_signature_can_verify_even_if_checksum_has_no_entry(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(release, "gpg_available", return_value=True):
                with mock.patch(
                    "frosted.cli.run_streaming", return_value=0
                ):
                    code, _text = self._run(
                        tmp,
                        f"{'0' * 64}  other.iso\n{'1' * 64}  another.iso\n",
                        signature=True,
                    )
        self.assertEqual(code, 0)


class BuildInfoTest(unittest.TestCase):
    def _make(self, tmp: str, recipe: Recipe) -> tuple[Path, dict]:
        root = Path(tmp)
        iso = root / "demo-1.0-amd64.iso"
        iso.write_bytes(b"fake iso content")

        recipe.path = root / "demo.toml"
        recipe.save(recipe.path)

        workdir = root / "build"
        workdir.mkdir()
        # dpkg の status を模したファイルを置く
        dpkg = workdir / "chroot" / "var" / "lib" / "dpkg"
        dpkg.mkdir(parents=True)
        (dpkg / "status").write_text(
            "Package: bash\n"
            "Status: install ok installed\n"
            "Architecture: amd64\n"
            "Version: 5.2.21-2\n"
            "\n"
            "Package: zlib1g\n"
            "Status: deinstall ok config-files\n"
            "Version: 1.2.13\n"
            "\n"
            "Package: vim\n"
            "Status: install ok installed\n"
            "Architecture: amd64\n"
            "Version: 2:9.0\n"
            "\n",
            encoding="utf-8",
        )

        digest = release.sha256_file(iso)
        path = release.write_build_info(
            recipe=recipe,
            iso_path=iso,
            digest=digest,
            workdir=workdir,
            bootappend="boot=live components",
            lb_args=["--distribution", "trixie"],
        )
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_writes_valid_json_with_expected_fields(self) -> None:
        recipe = Recipe()
        recipe.iso.name = "demo"
        recipe.iso.publisher = "Example Project"

        with tempfile.TemporaryDirectory() as tmp:
            path, info = self._make(tmp, recipe)

            self.assertEqual(path.name, "demo-1.0-amd64.iso.build-info.json")
            self.assertEqual(info["iso"]["publisher"], "Example Project")
            self.assertEqual(info["iso"]["architecture"], "amd64")
            self.assertEqual(info["iso"]["file"], "demo-1.0-amd64.iso")
            self.assertEqual(len(info["iso"]["sha256"]), 64)
            self.assertTrue(info["recipe"]["sha256"])

    def test_only_installed_packages_are_listed(self) -> None:
        """削除済みのパッケージが混ざると記録の意味がなくなる。"""
        recipe = Recipe()
        recipe.iso.name = "demo"

        with tempfile.TemporaryDirectory() as tmp:
            _path, info = self._make(tmp, recipe)

            names = [item["name"] for item in info["installed_packages"]]
            self.assertIn("bash", names)
            self.assertIn("vim", names)
            self.assertNotIn("zlib1g", names, "削除済みのパッケージが入っている")
            self.assertEqual(info["installed_package_count"], 2)

    def test_missing_chroot_is_not_fatal(self) -> None:
        """chroot が掃除されていてもレシピ情報だけで書けること。"""
        recipe = Recipe()
        recipe.iso.name = "demo"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso = root / "demo.iso"
            iso.write_bytes(b"x")
            path = release.write_build_info(
                recipe=recipe,
                iso_path=iso,
                digest=release.sha256_file(iso),
                workdir=root / "nonexistent",
                bootappend="",
                lb_args=[],
            )
            info = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(info["installed_packages"], [])
            self.assertEqual(info["installed_package_count"], 0)


class SigningAvailabilityTest(unittest.TestCase):
    def test_gpg_available_returns_bool(self) -> None:
        self.assertIsInstance(release.gpg_available(), bool)

    def test_missing_gpg_raises_a_helpful_error(self) -> None:
        from unittest import mock

        from frosted.errors import BuildError

        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "x.iso"
            iso.write_bytes(b"x")
            with mock.patch.object(release, "gpg_available", return_value=False):
                with self.assertRaises(BuildError) as caught:
                    release.sign_iso(iso, "nonexistent-key")
                self.assertIn("gnupg", caught.exception.hint or "")


class IsoMetadataTest(unittest.TestCase):
    def test_publisher_and_preparer_reach_lb_config(self) -> None:
        from frosted.backend.livebuild import build_lb_argv

        recipe = Recipe()
        recipe.iso.name = "demo"
        recipe.iso.publisher = "Example Project"
        recipe.iso.preparer = "Built by hand"
        recipe.iso.application = "demo-app"

        argv, _ = build_lb_argv(recipe)
        self.assertEqual(argv[argv.index("--iso-publisher") + 1], "Example Project")
        self.assertEqual(argv[argv.index("--iso-preparer") + 1], "Built by hand")
        self.assertEqual(argv[argv.index("--iso-application") + 1], "demo-app")

    def test_defaults_name_the_tool(self) -> None:
        from frosted import PROJECT_NAME
        from frosted.backend.livebuild import build_lb_argv

        recipe = Recipe()
        recipe.iso.name = "demo"

        argv, _ = build_lb_argv(recipe)
        self.assertIn(PROJECT_NAME, argv[argv.index("--iso-publisher") + 1])

    def test_roundtrip_keeps_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe = Recipe()
            recipe.iso.name = "demo"
            recipe.iso.publisher = "Example Project"
            recipe.iso.preparer = "The Maintainers"
            recipe.path = Path(tmp) / "demo.toml"
            recipe.save()

            loaded = Recipe.load(recipe.path)
            self.assertEqual(loaded.iso.publisher, "Example Project")
            self.assertEqual(loaded.iso.preparer, "The Maintainers")


if __name__ == "__main__":
    unittest.main()
