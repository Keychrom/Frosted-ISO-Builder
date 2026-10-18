"""レシピから live-build の設定ツリーを生成する。

live-build をそのまま使うと、利用者は config/ ツリー・auto/config・
3 段階のフックという 3 つの別々の仕組みを理解しないといけない。このモジュールの
仕事は、その全部をレシピ 1 枚から決定的に組み立てること。

方針として、生成するフックはすべて「冪等」に書く。live-build の再開機能や
`frosted gen` の再実行で同じ内容が二度適用されても壊れないようにするため。

なお auto/build と auto/clean はあえて生成しない。live-build は auto/ スクリプトを
対応する lb サブコマンドから自動で呼ぶため、auto/build の中で lb build を呼ぶと
再帰する可能性がある。ビルドの起動はこちらの runner が直接行うので不要。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import GENERATED_BY, __version__
from ..catalog import (
    KIOSK_AUTOSTART_PATH,
    KIOSK_LAUNCHER,
    KIOSK_URL_FILE,
    base_packages,
    desktop,
)
from ..errors import BuildError
from ..i18n import t, t_block
from ..recipe import Recipe

#: 生成物を追跡するファイル。再生成時に「前回作ったもの」だけを消すために使う。
MANIFEST_NAME = ".frosted-manifest.json"

#: ライブ起動時の後処理を置く場所
BOOT_LIB_DIR = "/usr/local/lib/frosted"
BOOT_SERVICE_NAME = "frosted-boot-setup.service"
FIRSTBOOT_SERVICE_NAME = "frosted-firstboot.service"

# --------------------------------------------------------------------------
# lb config のオプション名解決
# --------------------------------------------------------------------------

#: live-build のオプション名はバージョンによって単数形/複数形が揺れている。
#: 手元の lb がどちらの綴りを受け付けるか実行時に調べて、使えるほうを選ぶ。
#: 候補の並び順が「見つからなかったときに使う既定値」の優先順でもある。
OPTION_ALIASES: dict[str, tuple[str, ...]] = {
    "distribution": ("--distribution",),
    "architecture": ("--architecture", "--architectures"),
    "binary_image": ("--binary-image", "--binary-images"),
    "binary_filesystem": ("--binary-filesystem",),
    "checksums": ("--checksums",),
    "chroot_filesystem": ("--chroot-filesystem",),
    "squashfs_compression_type": ("--chroot-squashfs-compression-type",),
    "squashfs_compression_level": ("--chroot-squashfs-compression-level",),
    "initramfs_compression": ("--initramfs-compression",),
    "zsync": ("--zsync",),
    "win32_loader": ("--win32-loader",),
    "debconf_frontend": ("--debconf-frontend",),
    "debconf_priority": ("--debconf-priority",),
    "bootloaders": ("--bootloaders", "--bootloader"),
    "archive_areas": ("--archive-areas",),
    "mirror_bootstrap": ("--mirror-bootstrap",),
    "mirror_chroot": ("--mirror-chroot",),
    "mirror_binary": ("--mirror-binary",),
    "mirror_chroot_security": ("--mirror-chroot-security",),
    "mirror_binary_security": ("--mirror-binary-security",),
    "initramfs": ("--initramfs",),
    "initsystem": ("--initsystem",),
    "system": ("--system",),
    "debian_installer": ("--debian-installer",),
    "debian_installer_gui": ("--debian-installer-gui",),
    "debian_installer_distribution": ("--debian-installer-distribution",),
    "debian_installer_preseedfile": ("--debian-installer-preseedfile",),
    "updates": ("--updates",),
    "backports": ("--backports",),
    "proposed_updates": ("--proposed-updates",),
    "security": ("--security",),
    "source": ("--source",),
    "compression": ("--compression",),
    "apt_recommends": ("--apt-recommends",),
    "apt_http_proxy": ("--apt-http-proxy",),
    "apt_backend": ("--apt",),
    "apt_secure": ("--apt-secure",),
    "apt_source_archives": ("--apt-source-archives",),
    "apt_indices": ("--apt-indices",),
    "apt_options": ("--apt-options",),
    "apt_pipeline": ("--apt-pipeline",),
    "keyring_packages": ("--keyring-packages",),
    "cache": ("--cache",),
    "cache_stages": ("--cache-stages",),
    "iso_application": ("--iso-application",),
    "iso_publisher": ("--iso-publisher",),
    "iso_preparer": ("--iso-preparer",),
    "iso_volume": ("--iso-volume",),
    "bootappend_live": ("--bootappend-live",),
    "bootappend_live_failsafe": ("--bootappend-live-failsafe",),
    "bootappend_install": ("--bootappend-install",),
    "swap_file_path": ("--swap-file-path",),
    "swap_file_size": ("--swap-file-size",),
    "firmware_chroot": ("--firmware-chroot",),
    "firmware_binary": ("--firmware-binary",),
    "uefi_secure_boot": ("--uefi-secure-boot",),
    "image_name": ("--image-name",),
    "parent_distribution": ("--parent-distribution",),
    "debootstrap_options": ("--debootstrap-options",),
    "memtest": ("--memtest",),
    "utc_time": ("--utc-time",),
    "linux_packages": ("--linux-packages",),
    "linux_flavours": ("--linux-flavours",),
}

#: live-build に渡すつもりのない (存在しないかもしれない) オプションは
#: そもそも組み立てない。ここに無いキーを emit しようとすると例外になる。


class OptionSpellings:
    """`lb config --help` を読んで、実際に使える綴りを選ぶ。"""

    def __init__(self, supported: set[str] | None, probed: bool) -> None:
        self._supported = supported
        self.probed = probed
        self.notes: list[str] = []
        #: build_lb_args が「この lb には無い」と判断した設定キー。
        #: ブートローダの読み替えのような通常の警告と区別するために持つ。
        self.missing: list[str] = []

    def get(self, key: str) -> str | None:
        """キーに対応する実際のオプション名を返す。使えるものが無ければ None。"""
        aliases = OPTION_ALIASES.get(key)
        if aliases is None:
            raise KeyError(f"未定義の lb オプションキーです: {key}")

        if self._supported is None:
            # 調べられなかった (lb が無い / --help が読めない) ので既定の綴りを使う
            return aliases[0]

        for alias in aliases:
            if alias in self._supported:
                if alias != aliases[0]:
                    self.notes.append(
                        f"この live-build では {aliases[0]} の代わりに {alias} を使います。"
                    )
                return alias
        return None


_probe_cache: OptionSpellings | None = None


def probe_option_spellings(refresh: bool = False) -> OptionSpellings:
    """`lb config --help` から受け付け可能なオプション名を集める。

    lb が見つからない環境 (Windows での設定生成や --dry-run) では
    既定の綴りにフォールバックする。
    """
    global _probe_cache
    if _probe_cache is not None and not refresh:
        return _probe_cache

    if shutil.which("lb") is None:
        _probe_cache = OptionSpellings(None, probed=False)
        return _probe_cache

    try:
        proc = subprocess.run(
            ["lb", "config", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        _probe_cache = OptionSpellings(None, probed=False)
        return _probe_cache

    text = (proc.stdout or "") + (proc.stderr or "")
    found = set(re.findall(r"--[a-z0-9][a-z0-9-]*", text))
    _probe_cache = OptionSpellings(found or None, probed=bool(found))
    return _probe_cache


# --------------------------------------------------------------------------
# 結果
# --------------------------------------------------------------------------


@dataclass
class GenerationResult:
    workdir: Path
    created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bootappend: str = ""
    failsafe_append: str = ""
    lb_args: list[str] = field(default_factory=list)
    image_name: str = ""


# --------------------------------------------------------------------------
# ブートパラメータ
# --------------------------------------------------------------------------

#: ブートパラメータに埋め込む値から落とす文字。
#: カーネルコマンドラインは空白と引用符で分割されるので、これらが混ざると
#: パラメータの境界が壊れて起動しなくなる。
_BOOTAPPEND_UNSAFE = re.compile(r"[\s\"'\\]")

#: 利用者が追加するブートパラメータ用。
#: 空白は値の区切りとして意味があるので残し、引用符と制御文字だけを落とす。
_QUOTED_UNSAFE = re.compile(r"[\"'\\\r\n\t]")


def _boot_value(value: str) -> str:
    return _BOOTAPPEND_UNSAFE.sub("", value)


def build_bootappend(recipe: Recipe) -> str:
    """`--bootappend-live` に渡すカーネルパラメータを組み立てる。

    パラメータ名は live-config のマニュアルに合わせている。特に
    `locales=` は複数形、`keyboard-layouts=` はハイフン区切りなので注意。
    """
    params: list[str] = ["boot=live", "components"]

    def add(name: str, value: str) -> None:
        cleaned = _boot_value(value)
        if cleaned:
            params.append(f"{name}={cleaned}")

    add("hostname", recipe.system.resolved_hostname())
    add("username", recipe.user.name)
    # fullname はカーネルコマンドラインに載せない。live-build は
    # --bootappend-live の値を config/binary に引用符ごと書き出すが、
    # 値の中の " をエスケープしないため、user-fullname="Live User" が
    # config/binary を壊して `User ...: not found` でビルドが止まる。
    # 起動後の frosted-boot-setup で usermod -c を使って設定する。
    add("locales", recipe.system.locale)
    add("timezone", recipe.system.timezone)
    add("keyboard-layouts", recipe.system.keyboard_layout)
    add("keyboard-variants", recipe.system.keyboard_variant)
    add("keyboard-model", recipe.system.keyboard_model)

    profile = desktop(recipe.desktop.environment)
    session = recipe.desktop.session_manager or profile.x_session
    add("x-session-manager", session)

    if not recipe.user.autologin:
        params.append("noautologin")
    if not recipe.user.sudo:
        # live-config の noroot は sudo/policykit を無効にする
        params.append("noroot")
    if recipe.boot.persistence:
        params.append("persistence")

    # 利用者が直接書いた追加パラメータ。複数個を空白区切りで書けるので
    # 空白は残しつつ、引用符だけは落とす (残すとパラメータの切れ目が壊れる)。
    extra = _QUOTED_UNSAFE.sub("", recipe.boot.append).strip()
    if extra:
        params.append(extra)

    return " ".join(params)


def build_failsafe_append(recipe: Recipe) -> str:
    """failsafe メニュー用。トラブル時に使うので自動ログインは切っておく。"""
    params = ["boot=live", "components"]
    if recipe.boot.failsafe_noautologin:
        params.append("noautologin")
    params.append(f"locales={_boot_value(recipe.system.locale)}")
    return " ".join(params)


# --------------------------------------------------------------------------
# lb config の引数組み立て
# --------------------------------------------------------------------------


def _effective_bootloaders(recipe: Recipe) -> tuple[list[str], list[str]]:
    """アーキテクチャに合わないブートローダを落とす。

    syslinux は x86 専用なので arm64 では使えない。落としたものは警告として返す。
    """
    loaders = list(recipe.build.bootloaders)
    warnings: list[str] = []

    if recipe.iso.architecture == "arm64":
        # syslinux / grub-pc / grub-legacy は x86 用。arm64 では grub-efi
        # しか使えないので、指定されていても落とす。
        x86_loaders = {"syslinux", "grub-pc", "grub-legacy"}
        if any(loader in x86_loaders for loader in loaders):
            warnings.append(
                "arm64 では x86 用のブートローダ "
                "(syslinux/grub-pc/grub-legacy) を除外しました。"
            )
        loaders = [loader for loader in loaders if loader not in x86_loaders]
        if "grub-efi" not in loaders:
            loaders.append("grub-efi")
            warnings.append("arm64 では grub-efi を使います。")

    # 386 系は BIOS ブートも要るので syslinux を残す
    if not loaders:
        loaders = ["grub-efi"]
        warnings.append("ブートローダが空だったので grub-efi を使います。")

    return loaders, warnings


def build_lb_args(recipe: Recipe) -> tuple[list[str], list[str]]:
    """`lb config` に渡す引数を組み立てる。戻り値は (引数, 警告)。"""
    spellings = probe_option_spellings()
    spellings.missing.clear()
    args: list[str] = []
    warnings: list[str] = []

    def emit(key: str, *values: str) -> None:
        flag = spellings.get(key)
        if flag is None:
            spellings.missing.append(key)
            warnings.append(
                f"この live-build は {OPTION_ALIASES[key][0]} に対応していないため、"
                f"{key} の設定は反映されません。"
            )
            return
        args.append(flag)
        args.extend(values)

    loaders, loader_warnings = _effective_bootloaders(recipe)
    warnings.extend(loader_warnings)

    emit("distribution", recipe.iso.distribution)
    emit("architecture", recipe.iso.architecture)
    emit("binary_image", recipe.binary.image_type)
    if recipe.binary.filesystem:
        emit("binary_filesystem", recipe.binary.filesystem)
    emit("checksums", recipe.binary.checksums)
    if recipe.binary.chroot_filesystem:
        emit("chroot_filesystem", recipe.binary.chroot_filesystem)
    if recipe.binary.chroot_filesystem != "none":
        emit("squashfs_compression_type", recipe.binary.squashfs_compression)
        if recipe.binary.squashfs_compression_level is not None:
            emit(
                "squashfs_compression_level",
                str(recipe.binary.squashfs_compression_level),
            )
    if recipe.binary.initramfs_compression:
        emit("initramfs_compression", recipe.binary.initramfs_compression)
    if recipe.binary.zsync is not None:
        emit("zsync", "true" if recipe.binary.zsync else "false")
    if recipe.binary.win32_loader is not None:
        emit(
            "win32_loader",
            "true" if recipe.binary.win32_loader else "false",
        )
    if recipe.binary.swap_file_path:
        emit("swap_file_path", recipe.binary.swap_file_path)
        if recipe.binary.swap_file_size is not None:
            emit("swap_file_size", str(recipe.binary.swap_file_size))
    emit("bootloaders", " ".join(loaders))
    emit("archive_areas", " ".join(recipe.build.archive_areas))
    emit("mirror_bootstrap", recipe.build.mirror)
    emit("mirror_chroot", recipe.build.mirror)
    emit("mirror_binary", recipe.build.mirror)
    if recipe.build.security_mirror and recipe.iso.has_security_archive():
        emit("mirror_chroot_security", recipe.build.security_mirror)
        emit("mirror_binary_security", recipe.build.security_mirror)
    emit("parent_distribution", recipe.iso.distribution)
    emit("initramfs", recipe.build.initramfs or "live-boot")
    emit("initsystem", recipe.build.initsystem or "systemd")
    emit("system", "live")
    emit("debian_installer", recipe.installer.type or "none")
    if recipe.installer.gui is not None:
        emit(
            "debian_installer_gui",
            "true" if recipe.installer.gui else "false",
        )
    if recipe.installer.distribution:
        emit("debian_installer_distribution", recipe.installer.distribution)
    if recipe.installer.preseed and recipe.installer.type != "none":
        # config/preseed/*.cfg は installer ステージで
        # /install/preseed.cfg にまとめられる。起動時にそれを読ませる。
        emit("debian_installer_preseedfile", "/preseed.cfg")
    emit("compression", recipe.build.compression)
    emit("apt_recommends", "true" if recipe.build.apt_recommends else "false")
    if recipe.apt.backend:
        emit("apt_backend", recipe.apt.backend)
    if recipe.apt.secure is not None:
        emit("apt_secure", "true" if recipe.apt.secure else "false")
    if recipe.apt.source_archives is not None:
        emit(
            "apt_source_archives",
            "true" if recipe.apt.source_archives else "false",
        )
    if recipe.apt.indices is not None:
        emit("apt_indices", "true" if recipe.apt.indices else "false")
    if recipe.apt.options:
        emit("apt_options", recipe.apt.options)
    if recipe.apt.pipeline is not None:
        emit("apt_pipeline", str(recipe.apt.pipeline))
    if recipe.apt.keyring_packages:
        emit("keyring_packages", " ".join(recipe.apt.keyring_packages))
    if recipe.build.updates is not None:
        emit("updates", "true" if recipe.build.updates else "false")
    if recipe.build.backports is not None:
        emit("backports", "true" if recipe.build.backports else "false")
    if recipe.build.proposed_updates is not None:
        emit(
            "proposed_updates",
            "true" if recipe.build.proposed_updates else "false",
        )
    if recipe.build.security is not None:
        emit("security", "true" if recipe.build.security else "false")
    if recipe.build.source is not None:
        emit("source", "true" if recipe.build.source else "false")
    if recipe.build.debconf_frontend:
        emit("debconf_frontend", recipe.build.debconf_frontend)
    if recipe.build.debconf_priority:
        emit("debconf_priority", recipe.build.debconf_priority)
    emit("cache", "true" if recipe.build.cache else "false")
    if recipe.build.cache:
        emit("cache_stages", "bootstrap chroot")
    emit("firmware_chroot", "true" if recipe.build.firmware else "false")
    emit(
        "firmware_binary",
        "true" if recipe.build.firmware_binary else "false",
    )
    emit("uefi_secure_boot", recipe.build.secure_boot)
    emit("iso_application", recipe.iso.resolved_application())
    emit("iso_volume", recipe.iso.resolved_label())
    emit("iso_publisher", recipe.iso.resolved_publisher())
    emit("iso_preparer", recipe.iso.resolved_preparer())
    emit("image_name", recipe.iso.name)
    # live-build の --memtest は真偽値ではなく、どの memtest を入れるかの
    # 列挙値 (memtest86+ / memtest86 / none) を取る。true を渡すと
    # lb config が「不正な値」として終了してしまう。
    emit("memtest", "memtest86+" if recipe.build.memtest else "none")
    emit("utc_time", "true" if recipe.system.utc else "false")
    emit("bootappend_live", build_bootappend(recipe))
    emit("bootappend_live_failsafe", build_failsafe_append(recipe))
    extra_install = _QUOTED_UNSAFE.sub("", recipe.boot.install_append).strip()
    if extra_install:
        emit("bootappend_install", extra_install)
    if recipe.build.apt_proxy:
        emit("apt_http_proxy", recipe.build.apt_proxy)
    if recipe.build.debootstrap_options:
        emit("debootstrap_options", recipe.build.debootstrap_options)
    if recipe.kernel.packages:
        emit("linux_packages", recipe.kernel.packages)
    if recipe.kernel.flavours:
        emit("linux_flavours", " ".join(recipe.kernel.flavours))

    warnings.extend(spellings.notes)
    return args, warnings


def build_lb_argv(recipe: Recipe) -> tuple[list[str], list[str]]:
    """`lb config noauto ...` の完成形。"""
    args, warnings = build_lb_args(recipe)
    return ["lb", "config", "noauto", *args], warnings


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------


def generate(recipe: Recipe) -> GenerationResult:
    """レシピから live-build の設定ツリーを書き出す。"""
    workdir = recipe.workdir()
    result = GenerationResult(workdir=workdir, bootappend=build_bootappend(recipe))

    _clean_previous(workdir)
    _remove_livebuild_config_files(workdir)

    lb_args, warnings = build_lb_args(recipe)
    result.warnings.extend(warnings)
    result.lb_args = lb_args
    result.image_name = recipe.iso.name
    result.bootappend = build_bootappend(recipe)
    result.failsafe_append = build_failsafe_append(recipe)

    created: list[Path] = []

    created.append(
        _write_file(
            workdir / "auto" / "config", _generated(_auto_config(recipe)), 0o755
        )
    )
    for name, content, mode in _package_lists(recipe):
        created.append(
            _write_file(
                workdir / "config" / "package-lists" / name, _generated(content), mode
            )
        )
    for name, content in _hooks(recipe).items():
        created.append(
            _write_file(
                workdir / "config" / "hooks" / "live" / name,
                _generated(content),
                0o755,
            )
        )
    for name, content in _archive_lists(recipe).items():
        created.append(
            _write_file(
                workdir / "config" / "archives" / name, _generated(content), 0o644
            )
        )

    # live-build は config/archives/*.key.chroot をパッケージ導入前に
    # /etc/apt/trusted.gpg.d/ へ置く。ここに入れないと、extra_repositories の
    # 鍵がまだ無い状態で apt update が走ってしまう。
    for key_path in recipe.build.repository_keys:
        source = recipe.resolve(key_path)
        target = workdir / "config" / "archives" / f"{source.stem}.key.chroot"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)

    # live-build は config/packages.chroot/*_all.deb と
    # *_<arch>.deb からローカルリポジトリを作り、依存関係ごと導入する。
    for deb_path in recipe.packages.local:
        source = recipe.resolve(deb_path)
        target = workdir / "config" / "packages.chroot" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)

    if recipe.apt.preferences.strip():
        # config/archives/*.pref はパッケージ導入前に preferences.d へ入り、
        # 完成イメージにも残る (chroot 専用にしたいときは .pref.chroot)。
        # ユーザーが書いたピン留めの内容は訳さず、ヘッダだけ翻訳する。
        header = _generated(
            f"# {GENERATED_BY} が生成しました。\n\n"
        )
        content = header + recipe.apt.preferences.strip() + "\n"
        created.append(
            _write_file(
                workdir / "config" / "archives" / "frosted.pref", content, 0o644
            )
        )

    if recipe.installer.preseed and recipe.installer.type != "none":
        source = recipe.resolve(recipe.installer.preseed)
        # installer_preseed が config/preseed/*.cfg を連結して
        # /install/preseed.cfg を作る。
        target = workdir / "config" / "preseed" / "frosted.cfg"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)

    created.extend(_materialize_includes(recipe, workdir, result.warnings))
    created.append(
        _write_file(
            workdir / "README.build.md", _generated(_workdir_readme(recipe)), 0o644
        )
    )

    result.created = created
    _write_manifest(workdir, recipe, created)
    return result


def _clean_previous(workdir: Path) -> None:
    """前回このツールが作ったファイルだけを消す。

    workdir ごと消さないのは、live-build のブートストラップキャッシュや
    展開済み chroot を残して再ビルドを速くするため。
    """
    manifest_path = workdir / MANIFEST_NAME
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    for relative in manifest.get("files", []):
        target = workdir / relative
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists() or target.is_symlink():
                target.unlink()
        except OSError:
            # 消せなくても上書きはできるので致命傷にしない
            pass

    # 空になったディレクトリを片付ける (includes.chroot の残骸など)
    for root, dirs, files in os.walk(workdir, topdown=False):
        root_path = Path(root)
        if root_path == workdir:
            continue
        if root_path.name in ("auto", "config"):
            continue
        try:
            if not any(root_path.iterdir()):
                root_path.rmdir()
        except OSError:
            pass


def _remove_livebuild_config_files(workdir: Path) -> None:
    """live-build が書いた config 直下の設定ファイルを消す。

    `lb config` は既存の config/binary などを読み込んでから書き直す。
    以前のビルドで壊れた値が残っていると、新しい設定を書く前に
    読み込みで失敗してしまう。生成し直すときは毎回消す。
    config/package-lists などのサブディレクトリは残す。
    """
    config_dir = workdir / "config"
    if not config_dir.is_dir():
        return
    for entry in config_dir.iterdir():
        if not (entry.is_file() or entry.is_symlink()):
            continue
        try:
            entry.unlink()
        except OSError:
            # 消せなくても次の lb config が上書きするので致命傷にしない
            pass


def _write_manifest(workdir: Path, recipe: Recipe, created: list[Path]) -> None:
    manifest = {
        "generator": GENERATED_BY,
        "recipe": str(recipe.path) if recipe.path else None,
        "iso": recipe.iso.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [
            str(path.relative_to(workdir)).replace(os.sep, "/") for path in created
        ],
    }
    path = workdir / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )



def _generated(text: str) -> str:
    """このツールが書く文書を英語にする。

    利用者が書いた内容 (レシピの files.write や files.copy) は**訳さない**。
    持ち込んだファイルの中身は、そのまま入るのが当然だから。翻訳するのは
    このモジュールが組み立てた文書だけに限る。
    """
    return t_block(text)


def _write_file(path: Path, content: str, mode: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" は必須。既定のままだと Windows で CRLF になり、
    # シェルスクリプトが Linux 上で「bad interpreter: /bin/sh^M」で動かなくなる。
    path.write_text(content, encoding="utf-8", newline="\n")
    try:
        path.chmod(mode)
    except OSError:
        # Windows などで実行ビットが立てられないことがある。生成自体は成功とする。
        pass
    return path


# --------------------------------------------------------------------------
# auto/config
# --------------------------------------------------------------------------


def _auto_config(recipe: Recipe) -> str:
    """live-build が自動で呼ぶ設定スクリプト。

    中で `lb config noauto` を呼ぶのが必須。`noauto` を忘れると live-build が
    さらに auto/config を呼び、無限に再帰する。
    """
    argv, _warnings = build_lb_argv(recipe)
    lines = [
        "#!/bin/sh",
        "# " + GENERATED_BY + " がレシピから生成しました。手で編集しないでください。",
        "# 設定を変えたいときはレシピ (*.toml) を直して `frosted gen` を再実行します。",
        "#",
        "# noauto は必須です。外すと live-build が auto/config を呼び続けて再帰します。",
        "# 値は 1 つずつ shlex.quote で囲んであるので、空白入りの値もそのまま渡ります。",
        "",
        "set -e",
        "",
        "lb config \\",
    ]
    # argv は ["lb", "config", "noauto", ...] なので、2 番目 (noauto) から出す。
    for index in range(2, len(argv)):
        lines.append(f"\t{shlex.quote(argv[index])} \\")
    # ${@} は lb config と同じコマンドの引数として渡す。単独行にすると、
    # live-build が `lb config -- ...` で渡してくる追加オプションを
    # シェルがコマンド名として実行してしまう。
    lines.append('\t"${@}"')
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# パッケージリスト
# --------------------------------------------------------------------------


def _package_lists(recipe: Recipe) -> list[tuple[str, str, int]]:
    """config/package-lists/ に置くファイルを作る。"""
    lists: list[tuple[str, str, int]] = []

    base = list(base_packages())
    lists.append(("00-base.list.chroot", _format_packages(base), 0o644))

    profile = desktop(recipe.desktop.environment)
    if profile.packages:
        lists.append(
            (
                "10-desktop.list.chroot",
                _format_packages(list(profile.packages)),
                0o644,
            )
        )

    # extra_packages はデスクトップ環境に依存しない追加パッケージ。
    # CUI (environment = "none") でも言語パックなどを入れられるよう、
    # デスクトップのリストとは分けて必ず出力する。
    if recipe.desktop.extra_packages:
        lists.append(
            (
                "15-extra.list.chroot",
                _format_packages(recipe.desktop.extra_packages),
                0o644,
            )
        )

    if recipe.ssh.enable_server:
        lists.append(
            ("20-ssh.list.chroot", _format_packages(["openssh-server"]), 0o644)
        )

    if recipe.packages.include:
        lists.append(
            ("90-user.list.chroot", _format_packages(recipe.packages.include), 0o644)
        )

    return lists


def _format_packages(packages: list[str]) -> str:
    header = [
        "# " + GENERATED_BY + " が生成しました。",
        "# 1 行 1 パッケージ。このファイルを直接編集しても次の生成で上書きされます。",
        "# 追加したいパッケージはレシピの packages.include に書いてください。",
        "",
    ]
    return "\n".join(header + sorted(set(packages))) + "\n"


def _archive_lists(recipe: Recipe) -> dict[str, str]:
    """追加リポジトリ。設定されていなければ何も作らない。

    `.list.chroot` はビルド中の chroot だけで使われ、完成イメージからは
    取り除かれる。完成イメージでも apt を使えるようにしたい場合は
    `.list` にする (live-build が binary ステージでも読み直す)。
    """
    if not recipe.build.extra_repositories:
        return {}
    lines = [
        "# " + GENERATED_BY + " が生成しました。",
        "# レシピの build.extra_repositories の内容をそのまま展開しています。",
        "",
        *recipe.build.extra_repositories,
        "",
    ]
    name = "extra.list" if recipe.build.repositories_in_image else "extra.list.chroot"
    return {name: "\n".join(lines)}


# --------------------------------------------------------------------------
# ファイルの流し込み
# --------------------------------------------------------------------------


def _materialize_includes(
    recipe: Recipe, workdir: Path, warnings: list[str]
) -> list[Path]:
    """files.write / files.copy を config/includes.chroot に展開する。

    ここに置いたファイルはパッケージ導入より後に展開されるので、
    パッケージが入れたファイルを上書きできる。
    """
    root = workdir / "config" / "includes.chroot"
    created: list[Path] = []

    for entry in recipe.files.write:
        target = _safe_include_path(root, entry.path)
        created.append(_write_file(target, entry.content, _mode(entry.mode, 0o644)))

    for index, entry in enumerate(recipe.files.copy):
        source = recipe.resolve(entry.source)
        target = _safe_include_path(root, entry.target)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
            created.append(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            created.append(target)
        if entry.mode:
            try:
                target.chmod(_mode(entry.mode, 0o644))
            except OSError:
                pass

    for index, key_path in enumerate(recipe.ssh.authorized_keys):
        source = recipe.resolve(key_path)
        target = root / BOOT_LIB_DIR.lstrip("/") / "authorized_keys.d" / f"{index:02d}-{source.name}"
        created.append(_write_file(target, source.read_text(encoding="utf-8"), 0o644))

    if recipe.desktop.wallpaper and recipe.desktop.environment != "none":
        source = recipe.resolve(recipe.desktop.wallpaper)
        image_path = _wallpaper_image_path(recipe)
        target = root / image_path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)
        if recipe.desktop.environment != "kde":
            created.extend(_write_wallpaper_files(recipe, root, image_path))

    # signed-by= で参照される鍵は、パッケージ導入より前に chroot へ
    # 入れておく必要がある。includes.chroot はパッケージ導入後なので、
    # before_packages 側に置く。
    key_root = workdir / "config" / "includes.chroot_before_packages"
    for key_path in recipe.build.repository_keys:
        source = recipe.resolve(key_path)
        target = key_root / "usr" / "share" / "keyrings" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)

    # セットアップ / 初回起動スクリプトの実体。
    # フックとランナーはここに置かれたものを名前で呼ぶだけにしている。
    for key, scripts, subdir, mode in (
        ("setup", recipe.scripts.setup, "setup.d", 0o755),
        ("firstboot", recipe.scripts.firstboot, "firstboot.d", 0o755),
    ):
        for index, script in enumerate(scripts):
            source = recipe.resolve(script)
            name = f"{index:02d}-{source.name.replace(' ', '_')}"
            target = root / BOOT_LIB_DIR.lstrip("/") / subdir / name
            created.append(
                _write_file(target, source.read_text(encoding="utf-8"), mode)
            )

    return created


def _wallpaper_image_path(recipe: Recipe) -> str:
    suffix = recipe.resolve(recipe.desktop.wallpaper).suffix.lower()
    return f"/usr/share/backgrounds/frosted/wallpaper{suffix}"


def _wallpaper_script(recipe: Recipe, image_path: str) -> str:
    return f"""#!/bin/sh
# Set the desktop wallpaper configured in the recipe.
WALLPAPER="{image_path}"
[ -f "$WALLPAPER" ] || exit 0

case "${{XDG_CURRENT_DESKTOP:-}}" in
    *XFCE*)
        command -v xfconf-query >/dev/null 2>&1 || exit 0
        i=0
        while [ "$i" -lt 30 ]; do
            props=$(xfconf-query -c xfce4-desktop -l 2>/dev/null \\
                | grep '/backdrop/.*/last-image$' || true)
            if [ -n "$props" ]; then
                for prop in $props; do
                    xfconf-query -c xfce4-desktop -p "$prop" \\
                        -s "$WALLPAPER" >/dev/null 2>&1 || true
                done
                exit 0
            fi
            i=$((i + 1))
            sleep 1
        done
        ;;
    *GNOME*)
        command -v gsettings >/dev/null 2>&1 || exit 0
        gsettings set org.gnome.desktop.background picture-uri \\
            "file://$WALLPAPER" 2>/dev/null || true
        gsettings set org.gnome.desktop.background picture-uri-dark \\
            "file://$WALLPAPER" 2>/dev/null || true
        ;;
    *MATE*)
        command -v gsettings >/dev/null 2>&1 || exit 0
        gsettings set org.mate.background picture-filename \\
            "$WALLPAPER" 2>/dev/null || true
        ;;
    *Cinnamon*|*X-Cinnamon*)
        command -v gsettings >/dev/null 2>&1 || exit 0
        gsettings set org.cinnamon.desktop.background picture-uri \\
            "file://$WALLPAPER" 2>/dev/null || true
        ;;
    *LXQt*|*LXQT*)
        command -v pcmanfm-qt >/dev/null 2>&1 || exit 0
        pcmanfm-qt --set-wallpaper="$WALLPAPER" >/dev/null 2>&1 || true
        ;;
esac
exit 0
"""


def _write_wallpaper_files(
    recipe: Recipe, root: Path, image_path: str
) -> list[Path]:
    created: list[Path] = []
    script = root / "usr" / "local" / "bin" / "frosted-set-wallpaper"
    created.append(_write_file(script, _wallpaper_script(recipe, image_path), 0o755))

    autostart = (
        root / "etc" / "xdg" / "autostart" / "20-frosted-wallpaper.desktop"
    )
    created.append(
        _write_file(
            autostart,
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Frosted Wallpaper\n"
            "Comment=Set the wallpaper configured in the recipe\n"
            "Exec=/usr/local/bin/frosted-set-wallpaper\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n",
            0o644,
        )
    )
    return created


def _safe_include_path(root: Path, target: str) -> Path:
    """`/etc/motd` のようなイメージ内パスを includes.chroot 以下のパスに変換する。

    `..` や絶対パスのすり抜けで workdir の外に書かないよう、解決後の位置を必ず確認する。
    """
    relative = target.lstrip("/")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if not str(candidate).startswith(str(root_resolved) + os.sep) and candidate != root_resolved:
        raise BuildError(
            f"includes.chroot の外を指すパスです: {target}",
            hint="レシピの files セクションを見直してください。",
        )
    return candidate


def _mode(text: str, default: int) -> int:
    if not text:
        return default
    return int(text, 8)


# --------------------------------------------------------------------------
# フック
# --------------------------------------------------------------------------


def _hook_header(what: str) -> str:
    return (
        "#!/bin/sh\n"
        f"# {GENERATED_BY} が生成しました ({t(what)})。手で編集しないでください。\n"
        "# 変更したいときはレシピ (*.toml) を直して `frosted gen` を再実行します。\n"
        "\n"
        "set -e\n"
    )


def _hooks(recipe: Recipe) -> dict[str, str]:
    """config/hooks/live/ に置くフック。番号順に実行される。"""
    hooks: dict[str, str] = {}
    hooks["0100-system.hook.chroot"] = _hook_system(recipe)

    if recipe.user.autologin and desktop(recipe.desktop.environment).display_manager:
        hooks["0200-autologin.hook.chroot"] = _hook_autologin(recipe)
    if recipe.user.sudo:
        hooks["0300-sudo.hook.chroot"] = _hook_sudo(recipe)
    if recipe.ssh.enable_server:
        hooks["0400-ssh.hook.chroot"] = _hook_ssh(recipe)

    permissions = _hook_permissions(recipe)
    if permissions:
        hooks["0500-permissions.hook.chroot"] = permissions

    if _needs_boot_setup(recipe):
        hooks["0600-boot-setup.hook.chroot"] = _hook_boot_setup(recipe)
    if recipe.scripts.setup:
        hooks["0700-user-scripts.hook.chroot"] = _hook_user_scripts(recipe)
    if recipe.packages.exclude:
        hooks["0800-purge.hook.chroot"] = _hook_purge(recipe)

    hooks["0900-cleanup.hook.chroot"] = _hook_cleanup(recipe)
    return hooks


def _hook_system(recipe: Recipe) -> str:
    """ロケール・タイムゾーン・キーボード・ホスト名を焼き込む。

    ブートパラメータでも同じことを live-config が設定するが、こちらは
    「起動直後から正しい」状態にしておくためのもの。二重に設定しても壊れない。
    """
    locale = shlex.quote(recipe.system.locale)
    timezone = shlex.quote(recipe.system.timezone)
    layout = recipe.system.keyboard_layout
    variant = recipe.system.keyboard_variant
    model = recipe.system.keyboard_model or "pc105"
    hostname = shlex.quote(recipe.system.resolved_hostname())
    adjtime_clock = "UTC" if recipe.system.utc else "LOCAL"

    return f"""{_hook_header("システム設定")}
LOCALE={locale}
TIMEZONE={timezone}

# --- ロケール ---
if [ -f /etc/locale.gen ]; then
    # 該当行のコメントを外す。見つからなければ何も起きない。
    sed -i "s|^#[[:space:]]*\\(${{LOCALE}}[[:space:]]\\)|\\1|" /etc/locale.gen || true
fi
if command -v locale-gen >/dev/null 2>&1; then
    locale-gen || true
fi
if command -v update-locale >/dev/null 2>&1; then
    update-locale LANG="${{LOCALE}}" || true
fi

# --- タイムゾーン ---
if [ -f "/usr/share/zoneinfo/${{TIMEZONE}}" ]; then
    ln -sf "/usr/share/zoneinfo/${{TIMEZONE}}" /etc/localtime
    printf '%s\\n' "${{TIMEZONE}}" > /etc/timezone
else
    echo "frosted: タイムゾーンが見つかりません: ${{TIMEZONE}}" >&2
fi
printf '0.0 0 0.0\\n0\\n%s\\n' {shlex.quote(adjtime_clock)} > /etc/adjtime

# --- キーボード ---
cat > /etc/default/keyboard <<'KEYBOARD_EOF'
XKBMODEL={shlex.quote(model)}
XKBLAYOUT={shlex.quote(layout)}
XKBVARIANT={shlex.quote(variant)}
XKBOPTIONS=""
BACKSPACE="guess"
KEYBOARD_EOF

# --- ホスト名 ---
printf '%s\\n' {hostname} > /etc/hostname
cat > /etc/hosts <<HOSTS_EOF
127.0.0.1\tlocalhost
127.0.1.1\t{_boot_value(recipe.system.resolved_hostname())}

::1\t\tlocalhost ip6-localhost ip6-loopback
ff02::1\t\tip6-allnodes
ff02::2\t\tip6-allrouters
HOSTS_EOF
"""


def _hook_autologin(recipe: Recipe) -> str:
    """ディスプレイマネージャの自動ログインを設定する。

    どのファイルを書くかはディスプレイマネージャごとに違うので、
    インストールされているものを見て分岐する。live-config 側でも
    自動ログインは面倒を見てくれるが、こちらで明示しておくほうが確実。
    """
    profile = desktop(recipe.desktop.environment)
    dm = profile.display_manager
    user = shlex.quote(recipe.user.name)
    session = profile.autologin_session
    x_session = recipe.desktop.session_manager or profile.x_session

    parts = [_hook_header("自動ログイン設定"), f"USERNAME={user}", ""]

    if dm == "lightdm":
        parts.append(
            f"""# --- lightdm ---
if [ -d /etc/lightdm ]; then
    mkdir -p /etc/lightdm/lightdm.conf.d
    cat > /etc/lightdm/lightdm.conf.d/50-frosted.conf <<LIGHTDM_EOF
[Seat:*]
autologin-user=${{USERNAME}}
autologin-user-timeout=0
autologin-session={session}
user-session={session}
LIGHTDM_EOF
else
    echo "frosted: lightdm が見つかりません。自動ログインは設定されません。" >&2
fi
"""
        )
    elif dm == "sddm":
        parts.append(
            f"""# --- sddm ---
if [ -d /etc/sddm.conf.d ] || [ -f /etc/sddm.conf ]; then
    mkdir -p /etc/sddm.conf.d
    cat > /etc/sddm.conf.d/50-frosted.conf <<SDDM_EOF
[Autologin]
User=${{USERNAME}}
Session={session}.desktop
Relogin=true
SDDM_EOF
else
    echo "frosted: sddm が見つかりません。自動ログインは設定されません。" >&2
fi
"""
        )
    elif dm == "gdm3":
        parts.append(
            f"""# --- gdm3 ---
if [ -d /etc/gdm3 ]; then
    if [ -f /etc/gdm3/daemon.conf ]; then
        # [daemon] セクションに自動ログインの設定を足す
        if grep -q '^\\[daemon\\]' /etc/gdm3/daemon.conf; then
            sed -i '/^\\[daemon\\]/a AutomaticLoginEnable=true\\nAutomaticLogin='"${{USERNAME}}" /etc/gdm3/daemon.conf
        else
            printf '\\n[daemon]\\nAutomaticLoginEnable=true\\nAutomaticLogin=%s\\n' "${{USERNAME}}" >> /etc/gdm3/daemon.conf
        fi
    else
        printf '[daemon]\\nAutomaticLoginEnable=true\\nAutomaticLogin=%s\\n' "${{USERNAME}}" > /etc/gdm3/daemon.conf
    fi
else
    echo "frosted: gdm3 が見つかりません。自動ログインは設定されません。" >&2
fi
"""
        )

    # X セッションの選択はディスプレイマネージャ側の設定
    # (lightdm の user-session=、sddm の Session=) で行う。
    # /etc/X11/Xsession.d/ に細工を入れる方法もあるが、あそこは source される
    # 前提のディレクトリで exec を混ぜると挙動が読みにくくなるため避けている。
    # デスクトップ環境のセッションは x-session-manager ブートパラメータで
    # 指定済み (_hook_system ではなく build_bootappend 側)。
    if x_session:
        parts.append(f"# X セッション: {x_session} (ブートパラメータで指定済み)\n")

    return "\n".join(parts)


def _hook_sudo(recipe: Recipe) -> str:
    """ライブユーザーにパスワードなしの sudo を与える。

    Debian の公式 Live イメージと同じ挙動。ライブ環境ではパスワードが
    揮発するので、毎回聞かれないようにしておくのが自然。
    """
    user = shlex.quote(recipe.user.name)
    return f"""{_hook_header("sudo 設定")}
mkdir -p /etc/sudoers.d
cat > /etc/sudoers.d/010-frosted <<SUDOERS_EOF
# {GENERATED_BY} が生成しました。
# ライブユーザーはパスワードなしで sudo できる。
{recipe.user.name} ALL=(ALL) NOPASSWD: ALL
SUDOERS_EOF
chmod 0440 /etc/sudoers.d/010-frosted

# 書式が壊れていると sudo が全く使えなくなるので、ここで検証しておく
if command -v visudo >/dev/null 2>&1; then
    visudo -c -f /etc/sudoers.d/010-frosted >/dev/null
fi
"""


def _hook_ssh(recipe: Recipe) -> str:
    """sshd の設定を置く。公開鍵の配備は起動時に行う (0300 のブート処理)。"""
    lines = [
        _hook_header("SSH 設定"),
        "mkdir -p /etc/ssh/sshd_config.d",
        "cat > /etc/ssh/sshd_config.d/10-frosted.conf <<'SSHD_EOF'",
        f"# {GENERATED_BY} が生成しました。",
        f"PermitRootLogin {'yes' if recipe.ssh.permit_root_login else 'no'}",
        f"PasswordAuthentication {'yes' if recipe.ssh.password_authentication else 'no'}",
        "KbdInteractiveAuthentication no",
        "UsePAM yes",
        "SSHD_EOF",
        "",
    ]
    if not recipe.ssh.authorized_keys:
        lines.append(
            "# 公開鍵はレシピで指定されていない。パスワード認証が無効なら SSH ログインできない。\n"
        )
    return "\n".join(lines)


def _hook_permissions(recipe: Recipe) -> str:
    """files で指定されたパーミッションと所有者を適用する。

    includes.chroot からの展開では所有者を確実に設定できないので、
    chroot 内で root として実行されるここでまとめて直す。
    """
    entries: list[tuple[str, str, str]] = []
    for entry in recipe.files.copy:
        if entry.mode or entry.owner:
            entries.append((entry.target, entry.mode, entry.owner))
    for entry in recipe.files.write:
        if entry.mode or entry.owner:
            entries.append((entry.path, entry.mode, entry.owner))
    if not entries:
        return ""

    lines = [_hook_header("パーミッション設定")]
    for target, mode, owner in entries:
        quoted = shlex.quote(target)
        lines.append(f"if [ -e {quoted} ]; then")
        if mode:
            lines.append(f"    chmod {shlex.quote(mode)} {quoted} || true")
        if owner:
            lines.append(f"    chown {shlex.quote(owner)} {quoted} || true")
        lines.append("fi")
    lines.append("")
    return "\n".join(lines)


def _needs_boot_setup(recipe: Recipe) -> bool:
    return bool(
        recipe.user.password
        or recipe.user.root_password
        or recipe.user.default_groups
        or recipe.ssh.authorized_keys
        or recipe.user.autologin
        or recipe.user.fullname
        or recipe.scripts.firstboot
    )


def _split_groups(text: str) -> list[str]:
    """`sudo,audio` のような指定を分解する。カンマでも空白でも受ける。"""
    return [item for item in re.split(r"[,\s]+", text.strip()) if item]


def _boot_setup_script(recipe: Recipe) -> str:
    """ライブ起動時に流す後処理。

    live-config がライブユーザーを作るのは「起動時」なので、ユーザーに
    紐づく設定 (パスワード・グループ・SSH 鍵) はビルド時には書けない。
    ここにまとめて、起動後に一度だけ実行する。
    """
    user = recipe.user.name
    lines = [
        "#!/bin/sh",
        f"# {GENERATED_BY} が生成しました。",
        "# live-config がライブユーザーを作ったあとに 1 度だけ実行されます。",
        "# すべての操作は何度実行しても同じ結果になるように書いています。",
        "",
        f"USERNAME={shlex.quote(user)}",
        f"BASEDIR={shlex.quote(BOOT_LIB_DIR)}",
        "",
        'log() { echo "frosted: $*"; }',
        "",
        "# --- 自動ログイン用グループ ---",
        "if ! getent group autologin >/dev/null 2>&1; then",
        "    groupadd -r autologin 2>/dev/null || true",
        "fi",
        "",
        "# --- ライブユーザーができるのを待つ ---",
        "# このユニットは After=live-config.service で順序を指定しているが、",
        "# ユニット名が違う環境では順序が効かず、ユーザー作成より先に走りうる。",
        "# その場合は黙って諦めず、少しの間待ってからやり直す。",
        "attempt=0",
        'while [ "${attempt}" -lt 30 ]; do',
        '    if getent passwd "${USERNAME}" >/dev/null 2>&1; then',
        "        break",
        "    fi",
        "    attempt=$((attempt + 1))",
        "    sleep 1",
        "done",
        "",
        'if ! getent passwd "${USERNAME}" >/dev/null 2>&1; then',
        '    log "ユーザー ${USERNAME} が 30 秒待っても見つかりません。"',
        '    log "live-config がユーザーを作れなかった可能性があります。次のコマンドで確認してください:"',
        '    log "  journalctl -u live-config"',
        "    exit 0",
        "fi",
        "",
    ]

    if recipe.user.fullname:
        lines += [
            "# --- フルネーム ---",
            f"FULLNAME={shlex.quote(recipe.user.fullname)}",
            'if usermod -c "${FULLNAME}" "${USERNAME}"; then',
            '    log "フルネームを設定しました。"',
            "else",
            '    log "フルネームを設定できませんでした。"',
            "fi",
            "",
        ]

    if recipe.user.autologin:
        lines += [
            "# --- 自動ログイン ---",
            'if getent group autologin >/dev/null 2>&1; then',
            '    usermod -aG autologin "${USERNAME}" || true',
            "fi",
            "",
        ]

    if recipe.user.default_groups:
        # グループがまだ無い場合もあるので、作ってから所属させる。
        # 失敗してもログイン自体はできるようにしておく (権限が足りないだけ)。
        lines += ["# --- 追加のグループ ---"]
        for group in _split_groups(recipe.user.default_groups):
            quoted = shlex.quote(group)
            lines += [
                f"if ! getent group {quoted} >/dev/null 2>&1; then",
                f"    groupadd -r {quoted} 2>/dev/null || true",
                "fi",
                f"if getent group {quoted} >/dev/null 2>&1; then",
                f'    usermod -aG {quoted} "${{USERNAME}}" || true',
                "else",
                f'    log "グループ {group} を作れませんでした。"',
                "fi",
            ]
        lines.append("")

    if recipe.user.password:
        flag = " -e" if recipe.user.password_is_hashed() else ""
        lines += [
            "# --- ライブユーザーのパスワード ---",
            f"USER_PASSWORD={shlex.quote(recipe.user.password)}",
            'printf \'%s:%s\\n\' "${USERNAME}" "${USER_PASSWORD}" | chpasswd' + flag,
            'log "ライブユーザーのパスワードを設定しました。"',
            "",
        ]

    if recipe.user.root_password:
        flag = " -e" if recipe.user.root_password.startswith("$") else ""
        lines += [
            "# --- root のパスワード ---",
            f"ROOT_PASSWORD={shlex.quote(recipe.user.root_password)}",
            'printf \'%s:%s\\n\' root "${ROOT_PASSWORD}" | chpasswd' + flag,
            'log "root のパスワードを設定しました。"',
            "",
        ]

    if recipe.ssh.authorized_keys:
        lines += [
            "# --- SSH 公開鍵 ---",
            'if [ -d "${BASEDIR}/authorized_keys.d" ]; then',
            '    install -d -m 0700 -o "${USERNAME}" -g "${USERNAME}" "/home/${USERNAME}/.ssh"',
            '    cat "${BASEDIR}"/authorized_keys.d/* > "/home/${USERNAME}/.ssh/authorized_keys"',
            '    chown "${USERNAME}:${USERNAME}" "/home/${USERNAME}/.ssh/authorized_keys"',
            '    chmod 0600 "/home/${USERNAME}/.ssh/authorized_keys"',
            '    log "SSH 公開鍵を ${USERNAME} に配備しました。"',
            "fi",
            "",
        ]

    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def _firstboot_script(recipe: Recipe) -> str:
    """初回起動スクリプトのランナー。

    ライブ環境はルートが揮発するので、永続化を有効にしていない限り
    「初回」は毎回起動時になる。その挙動は README にも書いてある。
    """
    return f"""#!/bin/sh
# {GENERATED_BY} が生成しました。
# firstboot.d/ の中身を 1 度だけ実行します。
# 永続化 (persistence) を有効にしていない場合、ライブ環境は起動ごとに
# まっさらな状態に戻るため、実質「毎回」実行されます。

MARKER=/var/lib/frosted/firstboot-done

if [ -e "$MARKER" ]; then
    exit 0
fi

for script in /usr/local/lib/frosted/firstboot.d/*; do
    [ -e "$script" ] || continue
    [ -x "$script" ] || continue
    echo "frosted: 初回起動スクリプトを実行します: $script"
    if ! "$script"; then
        echo "frosted: 失敗しました: $script" >&2
    fi
done

mkdir -p "$(dirname "$MARKER")"
: > "$MARKER"
exit 0
"""


def _hook_boot_setup(recipe: Recipe) -> str:
    """起動時処理のスクリプトと systemd ユニットを仕込む。"""
    parts = [_hook_header("起動時の設定")]

    if _needs_boot_setup(recipe):
        parts.append(
            f"""# --- 起動時の設定スクリプト ---
mkdir -p {shlex.quote(BOOT_LIB_DIR)}
cat > {shlex.quote(BOOT_LIB_DIR + '/boot-setup.sh')} <<'BOOTSETUP_EOF'
{_boot_setup_script(recipe)}
BOOTSETUP_EOF
# root のパスワードなどが入るので、ライブユーザーからは読めないようにする。
# systemd は root で実行するため 0700 でも動く。
chmod 0700 {shlex.quote(BOOT_LIB_DIR + '/boot-setup.sh')}

cat > /etc/systemd/system/{BOOT_SERVICE_NAME} <<'UNIT_EOF'
[Unit]
Description=frosted live boot setup
After=live-config.service
Wants=live-config.service
Before=display-manager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={BOOT_LIB_DIR}/boot-setup.sh
StandardOutput=journal

[Install]
WantedBy=multi-user.target
UNIT_EOF

# chroot 内でも確実に効くよう、enable は systemctl ではなく直接シンボリックリンクで行う
mkdir -p /etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/{BOOT_SERVICE_NAME} \\
    /etc/systemd/system/multi-user.target.wants/{BOOT_SERVICE_NAME}
"""
        )

    if recipe.scripts.firstboot:
        parts.append(
            f"""# --- 初回起動スクリプト ---
mkdir -p {shlex.quote(BOOT_LIB_DIR + '/firstboot.d')}
cat > {shlex.quote(BOOT_LIB_DIR + '/firstboot.sh')} <<'FIRSTBOOT_EOF'
{_firstboot_script(recipe)}
FIRSTBOOT_EOF
chmod 0755 {shlex.quote(BOOT_LIB_DIR + '/firstboot.sh')}

cat > /etc/systemd/system/{FIRSTBOOT_SERVICE_NAME} <<'UNIT_EOF'
[Unit]
Description=frosted first boot scripts
After=multi-user.target {BOOT_SERVICE_NAME}
Wants={BOOT_SERVICE_NAME}

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={BOOT_LIB_DIR}/firstboot.sh
StandardOutput=journal

[Install]
WantedBy=multi-user.target
UNIT_EOF

mkdir -p /etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/{FIRSTBOOT_SERVICE_NAME} \\
    /etc/systemd/system/multi-user.target.wants/{FIRSTBOOT_SERVICE_NAME}
"""
        )

    return "\n".join(parts)


def _hook_user_scripts(recipe: Recipe) -> str:
    """レシピの scripts.setup を chroot 内で順に実行する。

    スクリプト本体は includes.chroot 経由でイメージに入れてあるので、
    ここではそれを実行するだけ。
    """
    lines = [_hook_header("利用者のセットアップスクリプト")]
    for index, script in enumerate(recipe.scripts.setup):
        name = f"{index:02d}-{Path(script).name.replace(' ', '_')}"
        path = f"{BOOT_LIB_DIR}/setup.d/{name}"
        lines += [
            f'echo "frosted: セットアップスクリプトを実行します: {name}"',
            f"if [ -x {shlex.quote(path)} ]; then",
            f"    {shlex.quote(path)}",
            "else",
            f'    echo "frosted: 実行できません (存在しないか実行権限なし): {path}" >&2',
            "    exit 1",
            "fi",
            "",
        ]
    return "\n".join(lines)


def _hook_purge(recipe: Recipe) -> str:
    """packages.exclude を実際に削除する。

    live-build のパッケージリストには「除外」の記法が無いので、
    インストール後に明示的に削除する。依存関係をたどって消すと
    必要なものまで落ちることがあるため、名指ししたものだけを消す。
    """
    packages = " ".join(shlex.quote(name) for name in recipe.packages.exclude)
    return f"""{_hook_header("除外パッケージの削除")}
# 名指しされたパッケージだけを削除する。依存関係の自動削除はしない。
export DEBIAN_FRONTEND=noninteractive
apt-get -y --purge remove {packages} || true
"""


def _hook_cleanup(recipe: Recipe) -> str:
    """イメージに残したくないものを消す。

    ビルドの痕跡 (apt のキャッシュ、ログ、machine-id) は
    ライブイメージを太らせるだけなので落とす。
    """
    return f"""{_hook_header("後片付け")}
export DEBIAN_FRONTEND=noninteractive

# APT のキャッシュとリスト
apt-get -y clean || true
apt-get -y autoclean || true
rm -rf /var/lib/apt/lists/* || true
rm -rf /var/cache/apt/archives/*.deb || true

# machine-id はコピー間で共有されると問題になるので消す。
# systemd が初回起動時に作り直す。
: > /etc/machine-id || true
rm -f /var/lib/dbus/machine-id || true
ln -sf /etc/machine-id /var/lib/dbus/machine-id 2>/dev/null || true

# ビルド中にできたログ
find /var/log -type f -exec truncate -s 0 {{}} + 2>/dev/null || true
rm -f /var/log/*.gz /var/log/*.[0-9] 2>/dev/null || true

# シェルの履歴
rm -f /root/.bash_history || true
rm -f /home/*/.bash_history || true

# 一時ファイル
rm -rf /tmp/* /var/tmp/* 2>/dev/null || true
"""


# --------------------------------------------------------------------------
# 生成物の説明書き
# --------------------------------------------------------------------------


def _workdir_readme(recipe: Recipe) -> str:
    output = recipe.iso.resolved_output()
    bootappend = build_bootappend(recipe)
    failsafe = build_failsafe_append(recipe)
    return f"""# このディレクトリについて

`{GENERATED_BY}` がレシピから生成した live-build の作業ディレクトリです。
**生成されたファイルを直接編集しないでください。** 次に生成したときに上書きされます。

設定を変えたいときはレシピファイルを直して、次のコマンドを実行してください。

```
frosted gen {recipe.path or "recipe.toml"}
```

## 手でビルドする

このツールを経由せず live-build を直接叩くこともできます。

```sh
cd {recipe.workdir()}
sudo lb build
```

`auto/config` が置いてあるので、`lb build` は自動的にレシピどおりの設定で
動きます。生成される ISO は `{output}` としてレシピと同じディレクトリに
コピーされます (このツール経由の場合)。

## 掃除

```sh
cd {recipe.workdir()}
sudo lb clean          # ビルド成果物だけ消す (キャッシュは残る)
sudo lb clean --purge  # 設定も含めて全部消す
```

## 設定の対応表

| どこ | 何が入っているか |
| --- | --- |
| `auto/config` | `lb config` に渡す全オプション。ここが実質の設定本体 |
| `config/package-lists/` | 入れるパッケージ (番号順に読み込まれる) |
| `config/packages.chroot/` | 同梱するローカル .deb (依存関係ごと導入される) |
| `config/includes.chroot/` | イメージにそのまま入れるファイル |
| `config/hooks/live/` | ビルド中に chroot 内で走るスクリプト。番号順 |
| `config/archives/` | 追加の APT リポジトリ |
| `config/archives/frosted.pref` | APT のピン留め |
| `{MANIFEST_NAME}` | このツールが生成したファイルの一覧 (掃除に使う) |

## ブートパラメータ

```
{bootappend}
```

failsafe エントリ:

```
{failsafe}
```
"""
