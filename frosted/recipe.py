"""レシピ (作りたい ISO の定義) のデータモデルと読み書き。

レシピは TOML にしている。人が読めてコメントも書けて、Debian 12 以降なら
標準ライブラリの tomllib だけで読めるので追加の依存が要らない。

書き出し側は自前で実装している。依存を増やしたくないのと、値の型が
限られている (文字列 / 真偽値 / 整数 / 文字列配列 / テーブル配列) ので
汎用ライブラリを入れるほどのものではないため。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import RecipeError

#: レシピフォーマットのバージョン。将来スキーマを変えたときの判別用。
RECIPE_VERSION = 1

#: 安定版。security アーカイブがある。
STABLE_DISTRIBUTIONS = ("bookworm", "trixie")
#: 開発版。testing は次の安定版、forky はその現在のコードネーム。
#: sid/unstable は security アーカイブを持たない。
ROLLING_DISTRIBUTIONS = ("testing", "forky", "sid", "unstable")
#: security アーカイブが存在しないもの。
UNSTABLE_DISTRIBUTIONS = ("sid", "unstable")
KNOWN_DISTRIBUTIONS = STABLE_DISTRIBUTIONS + ROLLING_DISTRIBUTIONS
KNOWN_ARCHITECTURES = ("amd64", "i386", "arm64")
KNOWN_ARCHIVE_AREAS = ("main", "contrib", "non-free", "non-free-firmware")
KNOWN_COMPRESSION = ("xz", "gzip", "bzip2", "lzip", "none")
KNOWN_BOOTLOADERS = ("syslinux", "grub-efi", "grub-pc", "grub-legacy")
KNOWN_SECURE_BOOT = ("auto", "enable", "disable")
KNOWN_APT_BACKENDS = ("apt", "apt-get", "aptitude")
KNOWN_INSTALLER_TYPES = (
    "none",
    "cdrom",
    "netinst",
    "netboot",
    "businesscard",
    "live",
)
KNOWN_BINARY_IMAGES = ("iso", "iso-hybrid", "netboot", "tar", "hdd")
KNOWN_BINARY_FILESYSTEMS = ("fat16", "fat32", "ext2", "ext3", "ext4", "ntfs")
KNOWN_CHROOT_FILESYSTEMS = ("ext2", "ext3", "ext4", "squashfs", "jffs2", "none")
KNOWN_CHECKSUMS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512", "none")
KNOWN_SQUASHFS_COMPRESSION = ("gzip", "lzma", "lzo", "lz4", "xz", "zstd")
KNOWN_INITRAMFS_COMPRESSION = ("bzip2", "gzip", "lzma")
KNOWN_DEBCONF_FRONTENDS = ("dialog", "editor", "noninteractive", "readline")
KNOWN_DEBCONF_PRIORITIES = ("low", "medium", "high", "critical")

DEFAULT_MIRROR = "http://deb.debian.org/debian/"
DEFAULT_SECURITY_MIRROR = "http://security.debian.org/debian-security/"

# 各値の書式。エラーメッセージで「どう書くべきか」を示すために使う。
RE_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*(:[a-z0-9-]+)?$")
RE_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RE_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
RE_ISO_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
# バージョンは出力ファイル名に入るので、パス区切りや空白を含めない。
RE_ISO_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*$")
RE_ISO_LABEL = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
# C.UTF-8 と POSIX は言語コードではないが実在するロケールなので許可する。
# 末尾の @modifier (de_DE@euro など) も見る。
RE_LOCALE = re.compile(
    r"^(C|POSIX|[a-z]{2,3}(_[A-Z]{2})?)(\.[A-Za-z0-9._-]+)?(@[A-Za-z0-9_+-]+)?$"
)
RE_KEYBOARD = re.compile(r"^[a-z]{2}(,[a-z]{2})*$")
RE_TIMEZONE = re.compile(r"^(UTC|[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z][A-Za-z0-9_+-]*)*)$")
RE_MIRROR = re.compile(r"^(https?|ftp|file)://")
RE_MODE = re.compile(r"^0?[0-7]{3,4}$")
RE_KEYRING_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: 壁紙として受け付ける拡張子。デスクトップ側の画像ローダに任せる。
WALLPAPER_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".svg")


# --------------------------------------------------------------------------
# 検証結果
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    """レシピ検証で見つかった 1 件の問題。"""

    level: str  # "error" か "warning"
    where: str  # "iso.name" のような場所
    message: str
    hint: str = ""

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    def render(self) -> str:
        return f"{self.where}: {self.message}"


class RecipeProblems(RecipeError):
    """検証エラーをまとめて運ぶための例外。"""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        lines = "\n".join(f"  - {issue.render()}" for issue in issues if issue.is_error)
        super().__init__(f"レシピに {sum(1 for i in issues if i.is_error)} 件のエラーがあります:\n{lines}")


# --------------------------------------------------------------------------
# セクション
# --------------------------------------------------------------------------


@dataclass
class IsoSection:
    name: str = ""
    version: str = "1.0"
    label: str = ""
    distribution: str = "trixie"
    architecture: str = "amd64"
    output: str = ""
    #: ISO のメタデータに書き込む作成者。配布するなら必ず設定する。
    #: 未指定だとツール名が入るので、公開するイメージでは書き換えること。
    publisher: str = ""
    preparer: str = ""
    #: ISO アプリケーション識別子。未指定なら name を使う。
    application: str = ""

    def is_rolling(self) -> bool:
        return self.distribution in ROLLING_DISTRIBUTIONS

    def has_security_archive(self) -> bool:
        return self.distribution not in UNSTABLE_DISTRIBUTIONS

    def resolved_label(self) -> str:
        """ISO のボリュームラベル。未指定なら名前から作る。"""
        if self.label:
            return self.label
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", self.name).strip("_").upper()
        return cleaned[:32] or "LINUX"

    def resolved_output(self) -> str:
        """出力 ISO のファイル名。未指定なら 名前-バージョン-arch.iso。"""
        if self.output:
            return self.output
        parts = [self.name or "linux"]
        if self.version:
            parts.append(self.version)
        parts.append(self.architecture)
        return "-".join(parts) + ".iso"

    def resolved_publisher(self) -> str:
        from . import PROJECT_NAME, __version__

        return self.publisher or f"{PROJECT_NAME} {__version__}"

    def resolved_preparer(self) -> str:
        from . import PROJECT_NAME, __version__

        return self.preparer or f"{PROJECT_NAME} {__version__}"

    def resolved_application(self) -> str:
        return self.application or self.name


@dataclass
class SystemSection:
    hostname: str = ""
    locale: str = "en_US.UTF-8"
    timezone: str = "UTC"
    keyboard_layout: str = "us"
    keyboard_variant: str = ""
    keyboard_model: str = ""
    utc: bool = True

    def resolved_hostname(self) -> str:
        return self.hostname or "debian"


@dataclass
class UserSection:
    name: str = "user"
    fullname: str = "Live User"
    #: 平文パスワード。`$` で始まる場合はハッシュ扱い (chpasswd -e)。
    password: str = ""
    root_password: str = ""
    default_groups: str = ""
    autologin: bool = True
    sudo: bool = True

    def password_is_hashed(self) -> bool:
        return self.password.startswith("$")


@dataclass
class DesktopSection:
    environment: str = "none"
    session_manager: str = ""
    #: 追加で入れるパッケージ (デスクトップ環境のプリセットに足す)
    extra_packages: list[str] = field(default_factory=list)
    #: ホスト上の壁紙画像。イメージ内にコピーしてログイン時に設定する。
    wallpaper: str = ""


@dataclass
class PackagesSection:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class SshSection:
    enable_server: bool = False
    authorized_keys: list[str] = field(default_factory=list)
    permit_root_login: bool = False
    password_authentication: bool = False


@dataclass
class CopyEntry:
    """ホスト上のファイル/ディレクトリをイメージにコピーする。"""

    source: str = ""
    target: str = ""
    mode: str = ""
    owner: str = ""


@dataclass
class WriteEntry:
    """中身を直接書いてイメージに置く。"""

    path: str = ""
    content: str = ""
    mode: str = "0644"
    owner: str = "root:root"


@dataclass
class FilesSection:
    copy: list[CopyEntry] = field(default_factory=list)
    write: list[WriteEntry] = field(default_factory=list)


@dataclass
class ScriptsSection:
    #: ビルド時に chroot 内で実行するスクリプト (ホスト上のパス)
    setup: list[str] = field(default_factory=list)
    #: 初回起動時に一度だけ実行するスクリプト (ホスト上のパス)
    firstboot: list[str] = field(default_factory=list)


@dataclass
class BootSection:
    #: bootappend-live にそのまま足す追加パラメータ
    append: str = ""
    persistence: bool = False
    #: failsafe メニューの自動ログインを無効にするか
    failsafe_noautologin: bool = True


@dataclass
class BinarySection:
    image_type: str = "iso-hybrid"
    #: hdd/netboot 用のファイルシステム。空なら live-build の既定値。
    filesystem: str = ""
    checksums: str = "sha256"
    chroot_filesystem: str = ""
    squashfs_compression: str = "xz"
    squashfs_compression_level: int | None = None
    initramfs_compression: str = ""
    zsync: bool | None = None
    win32_loader: bool | None = None


@dataclass
class AptSection:
    #: apt / apt-get / aptitude。空なら live-build の既定値。
    backend: str = ""
    secure: bool | None = None
    source_archives: bool | None = None
    indices: bool | None = None
    #: --apt-options に渡す 1 つの文字列。
    options: str = ""
    pipeline: int | None = None
    keyring_packages: list[str] = field(default_factory=list)


@dataclass
class InstallerSection:
    #: none / cdrom / netinst / netboot / businesscard / live
    type: str = "none"
    gui: bool | None = None
    distribution: str = ""
    #: ホスト上の preseed ファイル。config/debian-installer/preseed.cfg に置く。
    preseed: str = ""


@dataclass
class KernelSection:
    #: --linux-packages に渡す値 (例: linux-image)
    packages: str = ""
    #: --linux-flavours に渡す値 (例: amd64 / 686-pae)
    flavours: list[str] = field(default_factory=list)


@dataclass
class BuildSection:
    workdir: str = "build"
    mirror: str = DEFAULT_MIRROR
    security_mirror: str = DEFAULT_SECURITY_MIRROR
    archive_areas: list[str] = field(
        default_factory=lambda: ["main", "contrib", "non-free-firmware"]
    )
    compression: str = "xz"
    apt_recommends: bool = False
    cache: bool = True
    firmware: bool = True
    bootloaders: list[str] = field(default_factory=lambda: ["syslinux", "grub-efi"])
    secure_boot: str = "auto"
    memtest: bool = False
    #: APT の HTTP プロキシ。apt-cacher-ng などを挟むと再ビルドが速くなる。
    #: live-build の --apt-http-proxy に渡る。
    apt_proxy: str = ""
    debootstrap_options: str = ""
    #: 追加の APT リポジトリ (例: 独自リポジトリや backports)
    extra_repositories: list[str] = field(default_factory=list)
    #: extra_repositories で使う GPG 鍵 (ホスト上のパス)。
    #: /usr/share/keyrings/<ファイル名> にコピーされる。
    repository_keys: list[str] = field(default_factory=list)
    #: live-build の updates / backports / proposed-updates / security / source
    updates: bool | None = None
    backports: bool | None = None
    proposed_updates: bool | None = None
    security: bool | None = None
    source: bool | None = None
    debconf_frontend: str = ""
    debconf_priority: str = ""


# --------------------------------------------------------------------------
# レシピ本体
# --------------------------------------------------------------------------


@dataclass
class Recipe:
    iso: IsoSection = field(default_factory=IsoSection)
    system: SystemSection = field(default_factory=SystemSection)
    user: UserSection = field(default_factory=UserSection)
    desktop: DesktopSection = field(default_factory=DesktopSection)
    packages: PackagesSection = field(default_factory=PackagesSection)
    ssh: SshSection = field(default_factory=SshSection)
    files: FilesSection = field(default_factory=FilesSection)
    scripts: ScriptsSection = field(default_factory=ScriptsSection)
    boot: BootSection = field(default_factory=BootSection)
    build: BuildSection = field(default_factory=BuildSection)
    apt: AptSection = field(default_factory=AptSection)
    installer: InstallerSection = field(default_factory=InstallerSection)
    kernel: KernelSection = field(default_factory=KernelSection)
    binary: BinarySection = field(default_factory=BinarySection)

    #: レシピファイルの場所。相対パスはここを基準に解決する。
    path: Path | None = None

    # -- パス解決 ---------------------------------------------------------

    @property
    def base_dir(self) -> Path:
        if self.path is None:
            return Path.cwd()
        return self.path.parent

    def resolve(self, maybe_relative: str) -> Path:
        """レシピからの相対パスを絶対パスにする。"""
        candidate = Path(maybe_relative).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.base_dir / candidate).resolve()

    def workdir(self) -> Path:
        """live-build を走らせるディレクトリ。"""
        candidate = Path(self.build.workdir).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.base_dir / candidate).resolve()

    def output_path(self) -> Path:
        return self.base_dir / self.iso.resolved_output()

    # -- 読み書き ---------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Recipe":
        recipe_path = Path(path).expanduser().resolve()
        if not recipe_path.is_file():
            raise RecipeError(
                f"レシピファイルが見つかりません: {recipe_path}",
                hint="`frosted init` で新しく作れます。",
            )
        try:
            raw = recipe_path.read_bytes()
        except OSError as exc:
            raise RecipeError(f"レシピファイルを読めません: {exc}") from exc

        try:
            # Windows のエディタが付ける UTF-8 BOM を許容する。
            # tomllib は BOM をそのまま渡すと構文エラーになる。
            data = tomllib.loads(raw.decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise RecipeError(
                f"レシピファイルが UTF-8 ではありません: {recipe_path}",
                hint="文字コードを UTF-8 で保存し直してください。",
            ) from exc
        except tomllib.TOMLDecodeError as exc:
            raise RecipeError(
                f"レシピファイルの TOML 構文に誤りがあります: {exc}",
                hint=f"該当箇所を確認してください: {recipe_path}",
            ) from exc

        recipe = cls.from_dict(data, path=recipe_path)
        return recipe

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> "Recipe":
        """辞書から組み立てる。知らないキーはエラーとして記録する。"""
        issues: list[Issue] = []
        recipe = cls(path=path)

        # トップレベル: version だけを特別扱いする
        top_known = {
            "version",
            "iso",
            "system",
            "user",
            "desktop",
            "packages",
            "ssh",
            "files",
            "scripts",
            "boot",
            "build",
            "apt",
            "installer",
            "kernel",
            "binary",
        }
        _reject_unknown(data, top_known, "", issues)

        version = data.get("version", RECIPE_VERSION)
        if not isinstance(version, int):
            issues.append(
                Issue("error", "version", "整数で書いてください。", "例: version = 1")
            )
        elif version > RECIPE_VERSION:
            issues.append(
                Issue(
                    "error",
                    "version",
                    f"このツールが対応していないレシピバージョンです: {version}",
                    f"対応しているのは {RECIPE_VERSION} までです。ツールを更新してください。",
                )
            )

        recipe.iso = _iso_from(_table(data, "iso", issues), issues)
        recipe.system = _system_from(_table(data, "system", issues), issues)
        recipe.user = _user_from(_table(data, "user", issues), issues)
        recipe.desktop = _desktop_from(_table(data, "desktop", issues), issues)
        recipe.packages = _packages_from(_table(data, "packages", issues), issues)
        recipe.ssh = _ssh_from(_table(data, "ssh", issues), issues)
        recipe.files = _files_from(_table(data, "files", issues), issues)
        recipe.scripts = _scripts_from(_table(data, "scripts", issues), issues)
        recipe.boot = _boot_from(_table(data, "boot", issues), issues)
        recipe.build = _build_from(_table(data, "build", issues), issues)
        recipe.apt = _apt_from(_table(data, "apt", issues), issues)
        recipe.installer = _installer_from(
            _table(data, "installer", issues), issues
        )
        recipe.kernel = _kernel_from(_table(data, "kernel", issues), issues)
        recipe.binary = _binary_from(_table(data, "binary", issues), issues)

        _validate_cross(recipe, issues)
        errors = [issue for issue in issues if issue.is_error]
        if errors:
            raise RecipeProblems(issues)

        # 警告だけなら通すが、呼び出し側で拾えるように残しておく
        recipe.warnings = [issue for issue in issues if not issue.is_error]
        return recipe

    #: from_dict で見つかった警告 (エラーが無かった場合のみ設定される)
    warnings: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """TOML に書き出すための辞書。キーの順序がそのまま出力順になる。

        未設定の項目 (空文字と空配列) は落とす。既定値を全部書き出すと
        最小構成でも 80 行になってしまい、どこを変えればいいのか分からなく
        なるため。既定値の一覧は README を見てもらう。
        """
        data: dict[str, Any] = {"version": RECIPE_VERSION}

        data["iso"] = _clean(
            {
                "name": self.iso.name,
                "version": self.iso.version,
                "label": self.iso.label,
                "distribution": self.iso.distribution,
                "architecture": self.iso.architecture,
                "output": self.iso.output,
                "application": self.iso.application,
                "publisher": self.iso.publisher,
                "preparer": self.iso.preparer,
            },
            # version は空にすると出力ファイル名から省かれる意味のある値。
            # ここで落とすと再ロード時に既定の 1.0 に戻ってしまう。
            keep=("name", "version"),
        )

        data["system"] = _clean(
            {
                "hostname": self.system.hostname,
                "locale": self.system.locale,
                "timezone": self.system.timezone,
                "keyboard_layout": self.system.keyboard_layout,
                "keyboard_variant": self.system.keyboard_variant,
                "keyboard_model": self.system.keyboard_model,
                "utc": self.system.utc,
            }
        )

        data["user"] = _clean(
            {
                "name": self.user.name,
                "fullname": self.user.fullname,
                "password": self.user.password,
                "root_password": self.user.root_password,
                "default_groups": self.user.default_groups,
                "autologin": self.user.autologin,
                "sudo": self.user.sudo,
            },
            # fullname が空でも「表示名なし」という意味がある。
            keep=("name", "fullname"),
        )

        data["desktop"] = _clean(
            {
                "environment": self.desktop.environment,
                "session_manager": self.desktop.session_manager,
                "extra_packages": list(self.desktop.extra_packages),
                "wallpaper": self.desktop.wallpaper,
            }
        )

        packages = _clean(
            {
                "include": list(self.packages.include),
                "exclude": list(self.packages.exclude),
            }
        )
        if packages:
            data["packages"] = packages

        data["ssh"] = _clean(
            {
                "enable_server": self.ssh.enable_server,
                "authorized_keys": list(self.ssh.authorized_keys),
                "permit_root_login": self.ssh.permit_root_login,
                "password_authentication": self.ssh.password_authentication,
            }
        )

        files: dict[str, Any] = {}
        if self.files.copy:
            files["copy"] = [
                _clean(
                    {
                        "source": entry.source,
                        "target": entry.target,
                        "mode": entry.mode,
                        "owner": entry.owner,
                    }
                )
                for entry in self.files.copy
            ]
        if self.files.write:
            files["write"] = [
                _clean(
                    {
                        "path": entry.path,
                        "content": entry.content,
                        "mode": entry.mode,
                        "owner": entry.owner,
                    },
                    # 空の content は「空ファイルを作る」という意味なので残す。
                    keep=("path", "content"),
                )
                for entry in self.files.write
            ]
        if files:
            data["files"] = files

        scripts = _clean(
            {
                "setup": list(self.scripts.setup),
                "firstboot": list(self.scripts.firstboot),
            }
        )
        if scripts:
            data["scripts"] = scripts

        data["boot"] = _clean(
            {
                "append": self.boot.append,
                "persistence": self.boot.persistence,
                "failsafe_noautologin": self.boot.failsafe_noautologin,
            }
        )

        apt = _clean(
            {
                "backend": self.apt.backend,
                "secure": self.apt.secure,
                "source_archives": self.apt.source_archives,
                "indices": self.apt.indices,
                "options": self.apt.options,
                "pipeline": self.apt.pipeline,
                "keyring_packages": list(self.apt.keyring_packages),
            }
        )
        if apt:
            data["apt"] = apt

        installer = _clean(
            {
                "type": "" if self.installer.type == "none" else self.installer.type,
                "gui": self.installer.gui,
                "distribution": self.installer.distribution,
                "preseed": self.installer.preseed,
            }
        )
        if installer:
            data["installer"] = installer

        kernel = _clean(
            {
                "packages": self.kernel.packages,
                "flavours": list(self.kernel.flavours),
            }
        )
        if kernel:
            data["kernel"] = kernel

        binary = _clean(
            {
                "image_type": (
                    "" if self.binary.image_type == "iso-hybrid"
                    else self.binary.image_type
                ),
                "filesystem": self.binary.filesystem,
                "checksums": (
                    "" if self.binary.checksums == "sha256"
                    else self.binary.checksums
                ),
                "chroot_filesystem": self.binary.chroot_filesystem,
                "squashfs_compression": (
                    "" if self.binary.squashfs_compression == "xz"
                    else self.binary.squashfs_compression
                ),
                "squashfs_compression_level": self.binary.squashfs_compression_level,
                "initramfs_compression": self.binary.initramfs_compression,
                "zsync": self.binary.zsync,
                "win32_loader": self.binary.win32_loader,
            }
        )
        if binary:
            data["binary"] = binary

        data["build"] = _clean(
            {
                "workdir": self.build.workdir,
                "mirror": self.build.mirror,
                "security_mirror": self.build.security_mirror,
                "archive_areas": list(self.build.archive_areas),
                "compression": self.build.compression,
                "apt_recommends": self.build.apt_recommends,
                "cache": self.build.cache,
                "firmware": self.build.firmware,
                "bootloaders": list(self.build.bootloaders),
                "secure_boot": self.build.secure_boot,
                "memtest": self.build.memtest,
                "apt_proxy": self.build.apt_proxy,
                "debootstrap_options": self.build.debootstrap_options,
                "extra_repositories": list(self.build.extra_repositories),
                "repository_keys": list(self.build.repository_keys),
                "updates": self.build.updates,
                "backports": self.build.backports,
                "proposed_updates": self.build.proposed_updates,
                "security": self.build.security,
                "source": self.build.source,
                "debconf_frontend": self.build.debconf_frontend,
                "debconf_priority": self.build.debconf_priority,
            }
        )

        return data

    def dumps(self) -> str:
        return dumps(self.to_dict())

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path).expanduser().resolve() if path else self.path
        if target is None:
            raise RecipeError("保存先が指定されていません。")
        target.parent.mkdir(parents=True, exist_ok=True)
        # 改行は LF に固定する。Windows で作ったレシピを Debian に持っていく
        # ことがあるので、環境によって中身のバイト列が変わらないようにしたい。
        target.write_text(self.dumps(), encoding="utf-8", newline="\n")
        self.path = target
        return target


# --------------------------------------------------------------------------
# セクションの読み込み
# --------------------------------------------------------------------------


def _table(data: dict[str, Any], key: str, issues: list[Issue]) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append(
            Issue("error", key, f"[{key}] セクションはテーブルにしてください。")
        )
        return {}
    return value


#: 以前のバージョンにあって削った項目。理由を出さないと
#: 「綴りを間違えたのか、無くなったのか」が分からず混乱する。
REMOVED_KEYS: dict[str, str] = {
    "build.jobs": "live-build に並列度を指定するオプションが無いため削除しました。",
}


def _reject_unknown(
    data: dict[str, Any], known: set[str], prefix: str, issues: list[Issue]
) -> None:
    """知らないキーをエラーにする。

    レシピの打ち間違いは「黙って無視される」と原因が分からずハマるので、
    ここで確実に弾く。
    """
    for key in data:
        if key in known:
            continue
        where = f"{prefix}.{key}" if prefix else str(key)
        hint = REMOVED_KEYS.get(where, "綴りを確認してください。")
        issues.append(
            Issue(
                "error",
                where,
                f"知らない設定項目です: {key!r}",
                hint=hint,
            )
        )


def _str_value(
    data: dict[str, Any], key: str, default: str, where: str, issues: list[Issue]
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        issues.append(Issue("error", f"{where}.{key}", "文字列で書いてください。"))
        return default
    return value


def _bool_value(
    data: dict[str, Any], key: str, default: bool, where: str, issues: list[Issue]
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        issues.append(
            Issue(
                "error",
                f"{where}.{key}",
                "true か false で書いてください。",
                hint='文字列の "true" ではなく true と書きます。',
            )
        )
        return default
    return value


def _int_value(
    data: dict[str, Any], key: str, default: int, where: str, issues: list[Issue]
) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(Issue("error", f"{where}.{key}", "整数で書いてください。"))
        return default
    return value


def _optional_bool_value(
    data: dict[str, Any], key: str, where: str, issues: list[Issue]
) -> bool | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, bool):
        issues.append(
            Issue(
                "error",
                f"{where}.{key}",
                "true か false で書いてください。",
            )
        )
        return None
    return value


def _optional_int_value(
    data: dict[str, Any], key: str, where: str, issues: list[Issue]
) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(Issue("error", f"{where}.{key}", "整数で書いてください。"))
        return None
    return value


def _list_value(
    data: dict[str, Any], key: str, where: str, issues: list[Issue]
) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            Issue(
                "error",
                f"{where}.{key}",
                "配列で書いてください。",
                hint='例: ["vim", "curl"]',
            )
        )
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            issues.append(
                Issue("error", f"{where}.{key}[{index}]", "文字列で書いてください。")
            )
            continue
        result.append(item)
    return result


def _iso_from(data: dict[str, Any], issues: list[Issue]) -> IsoSection:
    known = {
        "name",
        "version",
        "label",
        "distribution",
        "architecture",
        "output",
        "publisher",
        "preparer",
        "application",
    }
    _reject_unknown(data, known, "iso", issues)
    section = IsoSection(
        name=_str_value(data, "name", "", "iso", issues),
        version=_str_value(data, "version", "1.0", "iso", issues),
        label=_str_value(data, "label", "", "iso", issues),
        distribution=_str_value(data, "distribution", "trixie", "iso", issues),
        architecture=_str_value(data, "architecture", "amd64", "iso", issues),
        output=_str_value(data, "output", "", "iso", issues),
        publisher=_str_value(data, "publisher", "", "iso", issues),
        preparer=_str_value(data, "preparer", "", "iso", issues),
        application=_str_value(data, "application", "", "iso", issues),
    )
    if not section.name:
        issues.append(
            Issue(
                "error",
                "iso.name",
                "ISO の名前は必須です。",
                hint='[iso] セクションに name = "mylinux" のように書いてください。',
            )
        )
    elif not RE_ISO_NAME.match(section.name):
        issues.append(
            Issue(
                "error",
                "iso.name",
                f"使えない名前です: {section.name!r}",
                hint="半角小文字・数字・ハイフンのみ。先頭と末尾はハイフン以外。例: my-linux-1",
            )
        )
    if section.version and not RE_ISO_VERSION.match(section.version):
        issues.append(
            Issue(
                "error",
                "iso.version",
                f"使えないバージョンです: {section.version!r}",
                hint="半角英数字と . _ + ~ - のみ。空白や / は使えません。",
            )
        )
    if section.distribution not in KNOWN_DISTRIBUTIONS:
        issues.append(
            Issue(
                "warning",
                "iso.distribution",
                f"動作確認していないリリースです: {section.distribution!r}",
                hint=f"対応: {', '.join(KNOWN_DISTRIBUTIONS)}",
            )
        )
    elif section.is_rolling():
        issues.append(
            Issue(
                "warning",
                "iso.distribution",
                "開発版 (testing/sid) です。"
                "ビルドや起動が壊れることがあります。",
                hint="安定版が必要なら trixie を使ってください。",
            )
        )
    if section.architecture not in KNOWN_ARCHITECTURES:
        issues.append(
            Issue(
                "error",
                "iso.architecture",
                f"未対応のアーキテクチャです: {section.architecture!r}",
                hint=f"対応: {', '.join(KNOWN_ARCHITECTURES)}",
            )
        )
    if section.label and not RE_ISO_LABEL.match(section.label):
        issues.append(
            Issue(
                "error",
                "iso.label",
                f"使えないラベルです: {section.label!r}",
                hint="半角英数字と _ . - のみ、32 文字以内。",
            )
        )
    if section.output:
        if "/" in section.output or "\\" in section.output:
            issues.append(
                Issue(
                    "error",
                    "iso.output",
                    "ファイル名だけを書いてください (ディレクトリは含められません)。",
                )
            )
        elif not section.output.endswith(".iso"):
            issues.append(
                Issue("error", "iso.output", "拡張子 .iso で終わる必要があります。")
            )
    return section


def _system_from(data: dict[str, Any], issues: list[Issue]) -> SystemSection:
    known = {
        "hostname",
        "locale",
        "timezone",
        "keyboard_layout",
        "keyboard_variant",
        "keyboard_model",
        "utc",
    }
    _reject_unknown(data, known, "system", issues)
    section = SystemSection(
        hostname=_str_value(data, "hostname", "", "system", issues),
        locale=_str_value(data, "locale", "en_US.UTF-8", "system", issues),
        timezone=_str_value(data, "timezone", "UTC", "system", issues),
        keyboard_layout=_str_value(data, "keyboard_layout", "us", "system", issues),
        keyboard_variant=_str_value(data, "keyboard_variant", "", "system", issues),
        keyboard_model=_str_value(data, "keyboard_model", "", "system", issues),
        utc=_bool_value(data, "utc", True, "system", issues),
    )
    if section.hostname and not RE_HOSTNAME.match(section.hostname):
        issues.append(
            Issue(
                "error",
                "system.hostname",
                f"使えないホスト名です: {section.hostname!r}",
                hint="半角小文字・数字・ハイフンのみ、63 文字以内。",
            )
        )
    if not RE_LOCALE.match(section.locale):
        issues.append(
            Issue(
                "error",
                "system.locale",
                f"使えないロケールです: {section.locale!r}",
                hint="例: ja_JP.UTF-8 / en_US.UTF-8 / C.UTF-8",
            )
        )
    if not RE_TIMEZONE.match(section.timezone):
        issues.append(
            Issue(
                "error",
                "system.timezone",
                f"使えないタイムゾーンです: {section.timezone!r}",
                hint="例: Asia/Tokyo / Europe/Berlin / UTC",
            )
        )
    if section.keyboard_layout and not RE_KEYBOARD.match(section.keyboard_layout):
        issues.append(
            Issue(
                "error",
                "system.keyboard_layout",
                f"使えないキーボード配列です: {section.keyboard_layout!r}",
                hint="2 文字の国コード。複数ならカンマ区切り。例: jp / us,us",
            )
        )
    return section


def _user_from(data: dict[str, Any], issues: list[Issue]) -> UserSection:
    known = {
        "name",
        "fullname",
        "password",
        "root_password",
        "default_groups",
        "autologin",
        "sudo",
    }
    _reject_unknown(data, known, "user", issues)
    section = UserSection(
        name=_str_value(data, "name", "user", "user", issues),
        fullname=_str_value(data, "fullname", "Live User", "user", issues),
        password=_str_value(data, "password", "", "user", issues),
        root_password=_str_value(data, "root_password", "", "user", issues),
        default_groups=_str_value(data, "default_groups", "", "user", issues),
        autologin=_bool_value(data, "autologin", True, "user", issues),
        sudo=_bool_value(data, "sudo", True, "user", issues),
    )
    if not RE_USERNAME.match(section.name):
        issues.append(
            Issue(
                "error",
                "user.name",
                f"使えないユーザー名です: {section.name!r}",
                hint="半角小文字で始まり、小文字・数字・_・- のみ、32 文字以内。",
            )
        )
    elif section.name == "root":
        issues.append(
            Issue(
                "error",
                "user.name",
                "root は使えません。一般ユーザー名を指定してください。",
            )
        )
    if ":" in section.default_groups or "\n" in section.default_groups:
        issues.append(
            Issue("error", "user.default_groups", "コロン (:) と改行は使えません。")
        )
    # fullname は起動後の usermod -c で設定する。GECOS の区切りである
    # コロンと改行だけを拒否する。引用符などは shlex.quote が守る。
    bad_fullname = sorted(set(section.fullname) & set("\n\r:"))
    if bad_fullname:
        issues.append(
            Issue(
                "error",
                "user.fullname",
                f"使えない文字が入っています: {' '.join(repr(c) for c in bad_fullname)}",
                hint="コロンと改行は使えません。",
            )
        )
    # chpasswd は「ユーザー名:パスワード」の 1 行を読むので、コロンと改行が混じると壊れる
    for key, value in (
        ("password", section.password),
        ("root_password", section.root_password),
    ):
        if ":" in value or "\n" in value:
            issues.append(
                Issue(
                    "error",
                    f"user.{key}",
                    "コロン (:) と改行は使えません。",
                    hint="パスワード設定は chpasswd に 1 行で渡すためです。",
                )
            )
    if section.password and section.password_is_hashed():
        if not section.password.startswith(("$1$", "$5$", "$6$", "$y$", "$2")):
            issues.append(
                Issue(
                    "warning",
                    "user.password",
                    "パスワードハッシュとして認識できない形式です。",
                    hint="平文ならそのまま、ハッシュなら $6$ などで始まる crypt(3) 形式にしてください。",
                )
            )
    return section


def _desktop_from(data: dict[str, Any], issues: list[Issue]) -> DesktopSection:
    known = {"environment", "session_manager", "extra_packages", "wallpaper"}
    _reject_unknown(data, known, "desktop", issues)
    return DesktopSection(
        environment=_str_value(data, "environment", "none", "desktop", issues),
        session_manager=_str_value(data, "session_manager", "", "desktop", issues),
        extra_packages=_list_value(data, "extra_packages", "desktop", issues),
        wallpaper=_str_value(data, "wallpaper", "", "desktop", issues),
    )


def _packages_from(data: dict[str, Any], issues: list[Issue]) -> PackagesSection:
    known = {"include", "exclude"}
    _reject_unknown(data, known, "packages", issues)
    section = PackagesSection(
        include=_list_value(data, "include", "packages", issues),
        exclude=_list_value(data, "exclude", "packages", issues),
    )
    for key, names in (("include", section.include), ("exclude", section.exclude)):
        for name in names:
            if not RE_PACKAGE_NAME.match(name):
                issues.append(
                    Issue(
                        "error",
                        f"packages.{key}",
                        f"パッケージ名として不正です: {name!r}",
                        hint="例: vim / curl / firefox-esr / libc6:amd64",
                    )
                )
    return section


def _ssh_from(data: dict[str, Any], issues: list[Issue]) -> SshSection:
    known = {
        "enable_server",
        "authorized_keys",
        "permit_root_login",
        "password_authentication",
    }
    _reject_unknown(data, known, "ssh", issues)
    return SshSection(
        enable_server=_bool_value(data, "enable_server", False, "ssh", issues),
        authorized_keys=_list_value(data, "authorized_keys", "ssh", issues),
        permit_root_login=_bool_value(data, "permit_root_login", False, "ssh", issues),
        password_authentication=_bool_value(
            data, "password_authentication", False, "ssh", issues
        ),
    )


def _owner_value(
    item: dict[str, Any], default: str, where: str, issues: list[Issue]
) -> str:
    """所有者を読む。旧名の Keychrom も受け付ける。"""
    owner = _str_value(item, "owner", default, where, issues)
    if "Keychrom" not in item:
        return owner

    old = _str_value(item, "Keychrom", "", where, issues)
    if "owner" in item:
        issues.append(
            Issue(
                "error",
                f"{where}.Keychrom",
                "owner と Keychrom は同時に指定できません。",
                hint="Keychrom は旧名です。owner だけを使ってください。",
            )
        )
    else:
        owner = old
        issues.append(
            Issue(
                "warning",
                f"{where}.Keychrom",
                "Keychrom は owner の旧名です。",
                hint="owner に書き換えてください。",
            )
        )
    return owner


def _files_from(data: dict[str, Any], issues: list[Issue]) -> FilesSection:
    _reject_unknown(data, {"copy", "write"}, "files", issues)
    section = FilesSection()

    raw_copy = data.get("copy", [])
    if not isinstance(raw_copy, list):
        issues.append(
            Issue(
                "error",
                "files.copy",
                "[[files.copy]] の配列にしてください。",
                hint="[[files.copy]] を 1 エントリごとに繰り返します。",
            )
        )
    else:
        for index, item in enumerate(raw_copy):
            where = f"files.copy[{index}]"
            if not isinstance(item, dict):
                issues.append(Issue("error", where, "テーブルにしてください。"))
                continue
            _reject_unknown(
                item, {"source", "target", "mode", "owner", "Keychrom"}, where, issues
            )
            entry = CopyEntry(
                source=_str_value(item, "source", "", where, issues),
                target=_str_value(item, "target", "", where, issues),
                mode=_str_value(item, "mode", "", where, issues),
                owner=_owner_value(item, "", where, issues),
            )
            if not entry.source:
                issues.append(Issue("error", f"{where}.source", "コピー元は必須です。"))
            if not entry.target:
                issues.append(Issue("error", f"{where}.target", "コピー先は必須です。"))
            elif not entry.target.startswith("/"):
                issues.append(
                    Issue(
                        "error",
                        f"{where}.target",
                        "イメージ内の絶対パスで書いてください。",
                        hint="例: /etc/motd",
                    )
                )
            elif ".." in Path(entry.target).parts:
                issues.append(Issue("error", f"{where}.target", ".. は使えません。"))
            if entry.mode and not RE_MODE.match(entry.mode):
                issues.append(
                    Issue(
                        "error",
                        f"{where}.mode",
                        f"使えないパーミッションです: {entry.mode!r}",
                        hint="例: 0644 / 0755 / 600",
                    )
                )
            section.copy.append(entry)

    raw_write = data.get("write", [])
    if not isinstance(raw_write, list):
        issues.append(
            Issue(
                "error",
                "files.write",
                "[[files.write]] の配列にしてください。",
                hint="[[files.write]] を 1 エントリごとに繰り返します。",
            )
        )
    else:
        for index, item in enumerate(raw_write):
            where = f"files.write[{index}]"
            if not isinstance(item, dict):
                issues.append(Issue("error", where, "テーブルにしてください。"))
                continue
            _reject_unknown(
                item, {"path", "content", "mode", "owner", "Keychrom"}, where, issues
            )
            entry = WriteEntry(
                path=_str_value(item, "path", "", where, issues),
                content=_str_value(item, "content", "", where, issues),
                mode=_str_value(item, "mode", "0644", where, issues),
                owner=_owner_value(item, "root:root", where, issues),
            )
            if not entry.path:
                issues.append(Issue("error", f"{where}.path", "パスは必須です。"))
            elif not entry.path.startswith("/"):
                issues.append(
                    Issue(
                        "error",
                        f"{where}.path",
                        "イメージ内の絶対パスで書いてください。",
                        hint="例: /etc/motd",
                    )
                )
            elif ".." in Path(entry.path).parts:
                issues.append(Issue("error", f"{where}.path", ".. は使えません。"))
            if entry.mode and not RE_MODE.match(entry.mode):
                issues.append(
                    Issue(
                        "error",
                        f"{where}.mode",
                        f"使えないパーミッションです: {entry.mode!r}",
                        hint="例: 0644 / 0755 / 600",
                    )
                )
            if "content" not in item:
                issues.append(Issue("error", f"{where}.content", "content が必要です。"))
            section.write.append(entry)

    return section


def _scripts_from(data: dict[str, Any], issues: list[Issue]) -> ScriptsSection:
    _reject_unknown(data, {"setup", "firstboot"}, "scripts", issues)
    return ScriptsSection(
        setup=_list_value(data, "setup", "scripts", issues),
        firstboot=_list_value(data, "firstboot", "scripts", issues),
    )


def _boot_from(data: dict[str, Any], issues: list[Issue]) -> BootSection:
    known = {"append", "persistence", "failsafe_noautologin"}
    _reject_unknown(data, known, "boot", issues)
    section = BootSection(
        append=_str_value(data, "append", "", "boot", issues),
        persistence=_bool_value(data, "persistence", False, "boot", issues),
        failsafe_noautologin=_bool_value(
            data, "failsafe_noautologin", True, "boot", issues
        ),
    )
    # 追加パラメータはカーネルコマンドラインにそのまま載る。
    # 引用符やバックスラッシュが混じるとパラメータの切れ目が壊れて起動しなくなる。
    bad = sorted(set(section.append) & set("\"'\\\n\r\t"))
    if bad:
        issues.append(
            Issue(
                "error",
                "boot.append",
                f"使えない文字が入っています: {' '.join(repr(c) for c in bad)}",
                hint="引用符やバックスラッシュは使えません。例: quiet splash toram",
            )
        )
    return section


def _build_from(data: dict[str, Any], issues: list[Issue]) -> BuildSection:
    known = {
        "workdir",
        "mirror",
        "security_mirror",
        "archive_areas",
        "compression",
        "apt_recommends",
        "cache",
        "firmware",
        "bootloaders",
        "secure_boot",
        "memtest",
        "apt_proxy",
        "debootstrap_options",
        "extra_repositories",
        "repository_keys",
        "updates",
        "backports",
        "proposed_updates",
        "security",
        "source",
        "debconf_frontend",
        "debconf_priority",
    }
    _reject_unknown(data, known, "build", issues)
    section = BuildSection(
        workdir=_str_value(data, "workdir", "build", "build", issues),
        mirror=_str_value(data, "mirror", DEFAULT_MIRROR, "build", issues),
        security_mirror=_str_value(
            data, "security_mirror", DEFAULT_SECURITY_MIRROR, "build", issues
        ),
        archive_areas=_list_value(data, "archive_areas", "build", issues)
        or ["main", "contrib", "non-free-firmware"],
        compression=_str_value(data, "compression", "xz", "build", issues),
        apt_recommends=_bool_value(data, "apt_recommends", False, "build", issues),
        cache=_bool_value(data, "cache", True, "build", issues),
        firmware=_bool_value(data, "firmware", True, "build", issues),
        bootloaders=_list_value(data, "bootloaders", "build", issues)
        or ["syslinux", "grub-efi"],
        secure_boot=_str_value(data, "secure_boot", "auto", "build", issues),
        memtest=_bool_value(data, "memtest", False, "build", issues),
        apt_proxy=_str_value(data, "apt_proxy", "", "build", issues),
        debootstrap_options=_str_value(
            data, "debootstrap_options", "", "build", issues
        ),
        extra_repositories=_list_value(
            data, "extra_repositories", "build", issues
        ),
        repository_keys=_list_value(
            data, "repository_keys", "build", issues
        ),
        updates=_optional_bool_value(data, "updates", "build", issues),
        backports=_optional_bool_value(data, "backports", "build", issues),
        proposed_updates=_optional_bool_value(
            data, "proposed_updates", "build", issues
        ),
        security=_optional_bool_value(data, "security", "build", issues),
        source=_optional_bool_value(data, "source", "build", issues),
        debconf_frontend=_str_value(
            data, "debconf_frontend", "", "build", issues
        ),
        debconf_priority=_str_value(
            data, "debconf_priority", "", "build", issues
        ),
    )
    if not section.workdir.strip() or "\n" in section.workdir or "\r" in section.workdir:
        issues.append(
            Issue(
                "error",
                "build.workdir",
                "作業ディレクトリが空か、改行を含んでいます。",
                hint="レシピの下の build など、通常のディレクトリ名を指定してください。",
            )
        )
    if not RE_MIRROR.match(section.mirror):
        issues.append(
            Issue(
                "error",
                "build.mirror",
                f"ミラー URL が不正です: {section.mirror!r}",
                hint="http:// https:// ftp:// file:// のいずれかで始めてください。",
            )
        )
    if section.security_mirror and not RE_MIRROR.match(section.security_mirror):
        issues.append(
            Issue(
                "error",
                "build.security_mirror",
                f"ミラー URL が不正です: {section.security_mirror!r}",
            )
        )
    for area in section.archive_areas:
        if area not in KNOWN_ARCHIVE_AREAS:
            issues.append(
                Issue(
                    "warning",
                    "build.archive_areas",
                    f"知らないアーカイブ領域です: {area!r}",
                    hint=f"通常は {', '.join(KNOWN_ARCHIVE_AREAS)} のいずれかです。",
                )
            )
    if section.compression not in KNOWN_COMPRESSION:
        issues.append(
            Issue(
                "error",
                "build.compression",
                f"未対応の圧縮方式です: {section.compression!r}",
                hint=f"対応: {', '.join(KNOWN_COMPRESSION)}",
            )
        )
    for loader in section.bootloaders:
        if loader not in KNOWN_BOOTLOADERS:
            issues.append(
                Issue(
                    "error",
                    "build.bootloaders",
                    f"未対応のブートローダです: {loader!r}",
                    hint=f"対応: {', '.join(KNOWN_BOOTLOADERS)}",
                )
            )
    if section.secure_boot not in KNOWN_SECURE_BOOT:
        issues.append(
            Issue(
                "error",
                "build.secure_boot",
                f"未対応の値です: {section.secure_boot!r}",
                hint=f"対応: {', '.join(KNOWN_SECURE_BOOT)}",
            )
        )
    if (
        section.debconf_frontend
        and section.debconf_frontend not in KNOWN_DEBCONF_FRONTENDS
    ):
        issues.append(
            Issue(
                "error",
                "build.debconf_frontend",
                f"未対応の debconf frontend です: {section.debconf_frontend!r}",
                hint=f"対応: {', '.join(KNOWN_DEBCONF_FRONTENDS)}",
            )
        )
    if (
        section.debconf_priority
        and section.debconf_priority not in KNOWN_DEBCONF_PRIORITIES
    ):
        issues.append(
            Issue(
                "error",
                "build.debconf_priority",
                f"未対応の debconf priority です: {section.debconf_priority!r}",
                hint=f"対応: {', '.join(KNOWN_DEBCONF_PRIORITIES)}",
            )
        )
    if section.apt_proxy and not RE_MIRROR.match(section.apt_proxy):
        issues.append(
            Issue(
                "error",
                "build.apt_proxy",
                f"プロキシ URL が不正です: {section.apt_proxy!r}",
                hint="例: http://192.168.1.10:3142",
            )
        )
    return section


# --------------------------------------------------------------------------
# セクションをまたぐ検証
# --------------------------------------------------------------------------


def _apt_from(data: dict[str, Any], issues: list[Issue]) -> AptSection:
    known = {
        "backend",
        "secure",
        "source_archives",
        "indices",
        "options",
        "pipeline",
        "keyring_packages",
    }
    _reject_unknown(data, known, "apt", issues)
    section = AptSection(
        backend=_str_value(data, "backend", "", "apt", issues),
        secure=_optional_bool_value(data, "secure", "apt", issues),
        source_archives=_optional_bool_value(
            data, "source_archives", "apt", issues
        ),
        indices=_optional_bool_value(data, "indices", "apt", issues),
        options=_str_value(data, "options", "", "apt", issues),
        pipeline=_optional_int_value(data, "pipeline", "apt", issues),
        keyring_packages=_list_value(
            data, "keyring_packages", "apt", issues
        ),
    )
    if section.backend and section.backend not in KNOWN_APT_BACKENDS:
        issues.append(
            Issue(
                "error",
                "apt.backend",
                f"未対応の APT バックエンドです: {section.backend!r}",
                hint=f"対応: {', '.join(KNOWN_APT_BACKENDS)}",
            )
        )
    if section.pipeline is not None and section.pipeline < 0:
        issues.append(
            Issue("error", "apt.pipeline", "0 以上で指定してください。")
        )
    for name in section.keyring_packages:
        if not RE_PACKAGE_NAME.match(name):
            issues.append(
                Issue(
                    "error",
                    "apt.keyring_packages",
                    f"パッケージ名として不正です: {name!r}",
                )
            )
    return section


def _installer_from(
    data: dict[str, Any], issues: list[Issue]
) -> InstallerSection:
    known = {"type", "gui", "distribution", "preseed"}
    _reject_unknown(data, known, "installer", issues)
    section = InstallerSection(
        type=_str_value(data, "type", "none", "installer", issues),
        gui=_optional_bool_value(data, "gui", "installer", issues),
        distribution=_str_value(data, "distribution", "", "installer", issues),
        preseed=_str_value(data, "preseed", "", "installer", issues),
    )
    if section.type not in KNOWN_INSTALLER_TYPES:
        issues.append(
            Issue(
                "error",
                "installer.type",
                f"未対応のインストーラー種別です: {section.type!r}",
                hint=f"対応: {', '.join(KNOWN_INSTALLER_TYPES)}",
            )
        )
    if section.distribution and not RE_ISO_VERSION.match(section.distribution):
        issues.append(
            Issue(
                "error",
                "installer.distribution",
                f"使えないリリース名です: {section.distribution!r}",
            )
        )
    return section


def _kernel_from(data: dict[str, Any], issues: list[Issue]) -> KernelSection:
    known = {"packages", "flavours"}
    _reject_unknown(data, known, "kernel", issues)
    section = KernelSection(
        packages=_str_value(data, "packages", "", "kernel", issues),
        flavours=_list_value(data, "flavours", "kernel", issues),
    )
    for flavour in section.flavours:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$", flavour):
            issues.append(
                Issue(
                    "error",
                    "kernel.flavours",
                    f"使えないフレーバー名です: {flavour!r}",
                )
            )
    return section


def _binary_from(data: dict[str, Any], issues: list[Issue]) -> BinarySection:
    known = {
        "image_type",
        "filesystem",
        "checksums",
        "chroot_filesystem",
        "squashfs_compression",
        "squashfs_compression_level",
        "initramfs_compression",
        "zsync",
        "win32_loader",
    }
    _reject_unknown(data, known, "binary", issues)
    section = BinarySection(
        image_type=_str_value(data, "image_type", "iso-hybrid", "binary", issues),
        filesystem=_str_value(data, "filesystem", "", "binary", issues),
        checksums=_str_value(data, "checksums", "sha256", "binary", issues),
        chroot_filesystem=_str_value(
            data, "chroot_filesystem", "", "binary", issues
        ),
        squashfs_compression=_str_value(
            data, "squashfs_compression", "xz", "binary", issues
        ),
        squashfs_compression_level=_optional_int_value(
            data, "squashfs_compression_level", "binary", issues
        ),
        initramfs_compression=_str_value(
            data, "initramfs_compression", "", "binary", issues
        ),
        zsync=_optional_bool_value(data, "zsync", "binary", issues),
        win32_loader=_optional_bool_value(data, "win32_loader", "binary", issues),
    )
    checks = (
        ("image_type", section.image_type, KNOWN_BINARY_IMAGES),
        ("filesystem", section.filesystem, KNOWN_BINARY_FILESYSTEMS),
        ("checksums", section.checksums, KNOWN_CHECKSUMS),
        (
            "chroot_filesystem",
            section.chroot_filesystem,
            KNOWN_CHROOT_FILESYSTEMS,
        ),
        (
            "squashfs_compression",
            section.squashfs_compression,
            KNOWN_SQUASHFS_COMPRESSION,
        ),
        (
            "initramfs_compression",
            section.initramfs_compression,
            KNOWN_INITRAMFS_COMPRESSION,
        ),
    )
    for key, value, allowed in checks:
        if value and value not in allowed:
            issues.append(
                Issue(
                    "error",
                    f"binary.{key}",
                    f"未対応の値です: {value!r}",
                    hint=f"対応: {', '.join(allowed)}",
                )
            )
    if (
        section.squashfs_compression_level is not None
        and section.squashfs_compression_level < 1
    ):
        issues.append(
            Issue(
                "error",
                "binary.squashfs_compression_level",
                "1 以上で指定してください。",
            )
        )
    return section


def _validate_cross(recipe: Recipe, issues: list[Issue]) -> None:
    from .catalog import DESKTOPS  # 循環インポートを避けるためここで読む

    if recipe.desktop.environment not in DESKTOPS:
        issues.append(
            Issue(
                "error",
                "desktop.environment",
                f"知らないデスクトップ環境です: {recipe.desktop.environment!r}",
                hint=f"選べるのは: {', '.join(sorted(DESKTOPS))}",
            )
        )

    # ブートローダとアーキテクチャの整合。syslinux は i386 でも使えるので、
    # arm64 のときだけ x86 用ブートローダを除外する。
    if recipe.iso.architecture == "arm64":
        x86_loaders = {"syslinux", "grub-pc", "grub-legacy"}
        if any(loader in x86_loaders for loader in recipe.build.bootloaders):
            issues.append(
                Issue(
                    "warning",
                    "build.bootloaders",
                    "arm64 では x86 用のブートローダ "
                    "(syslinux/grub-pc/grub-legacy) が使えません。除外されます。",
                    hint="arm64 は grub-efi のみを使います。",
                )
            )

    # ログイン手段が無くなる組み合わせを警告
    has_password = bool(recipe.user.password)
    if not recipe.user.autologin and not has_password:
        issues.append(
            Issue(
                "warning",
                "user.password",
                "自動ログインが無効で、パスワードも未設定です。このままだとログインできません。",
                hint="user.password を設定するか、user.autologin を true にしてください。",
            )
        )
    if recipe.desktop.environment == "none" and recipe.user.autologin:
        issues.append(
            Issue(
                "warning",
                "user.autologin",
                "デスクトップ環境が none なので、自動ログインはコンソール (tty) にのみ効きます。",
            )
        )

    # SSH で締め出される組み合わせを警告
    if recipe.ssh.enable_server:
        if not recipe.ssh.authorized_keys and not recipe.user.password:
            issues.append(
                Issue(
                    "warning",
                    "ssh.authorized_keys",
                    "SSH サーバーを有効にしますが、鍵もパスワードも未設定です。ログインできません。",
                    hint="ssh.authorized_keys に公開鍵のパスを書くか、user.password を設定してください。",
                )
            )
        if not recipe.ssh.password_authentication and not recipe.ssh.authorized_keys:
            issues.append(
                Issue(
                    "warning",
                    "ssh.enable_server",
                    "パスワード認証を無効にし、鍵も設定していません。SSH でログインできません。",
                )
            )

    # sid/unstable には security アーカイブが無い
    if (
        not recipe.iso.has_security_archive()
        and recipe.build.security_mirror
    ):
        issues.append(
            Issue(
                "warning",
                "build.security_mirror",
                "sid/unstable には security アーカイブがありません。"
                "build.security_mirror は使用しません。",
                hint="security 更新は unstable 経由で入ります。",
            )
        )

    # 永続化はパーティションの準備が要る
    if recipe.boot.persistence:
        issues.append(
            Issue(
                "warning",
                "boot.persistence",
                "永続化を有効にしました。USB 側に 'persistence' ラベルのパーティションと "
                "その直下の persistence.conf が別途必要です。",
            )
        )

    # setup スクリプトの実行順は重要なので、存在しないファイルはエラーにする
    for key, scripts in (
        ("scripts.setup", recipe.scripts.setup),
        ("scripts.firstboot", recipe.scripts.firstboot),
    ):
        for script in scripts:
            candidate = recipe.resolve(script)
            if not candidate.is_file():
                issues.append(
                    Issue(
                        "error",
                        key,
                        f"スクリプトが見つかりません: {script}",
                        hint=f"探した場所: {candidate}",
                    )
                )
    for entry in recipe.files.copy:
        if not entry.source:
            continue
        candidate = recipe.resolve(entry.source)
        if not candidate.exists():
            issues.append(
                Issue(
                    "error",
                    "files.copy",
                    f"コピー元が見つかりません: {entry.source}",
                    hint=f"探した場所: {candidate}",
                )
            )
    for key_path in recipe.ssh.authorized_keys:
        candidate = recipe.resolve(key_path)
        if not candidate.is_file():
            issues.append(
                Issue(
                    "error",
                    "ssh.authorized_keys",
                    f"公開鍵が見つかりません: {key_path}",
                    hint=f"探した場所: {candidate}",
                )
            )

    if recipe.installer.preseed:
        candidate = recipe.resolve(recipe.installer.preseed)
        if not candidate.is_file():
            issues.append(
                Issue(
                    "error",
                    "installer.preseed",
                    f"preseed ファイルが見つかりません: {recipe.installer.preseed}",
                    hint=f"探した場所: {candidate}",
                )
            )
        if recipe.installer.type == "none":
            issues.append(
                Issue(
                    "warning",
                    "installer.preseed",
                    "インストーラーが none のため、preseed は使われません。",
                )
            )

    if recipe.desktop.wallpaper:
        candidate = recipe.resolve(recipe.desktop.wallpaper)
        if not candidate.is_file():
            issues.append(
                Issue(
                    "error",
                    "desktop.wallpaper",
                    f"壁紙の画像が見つかりません: {recipe.desktop.wallpaper}",
                    hint=f"探した場所: {candidate}",
                )
            )
        elif candidate.suffix.lower() not in WALLPAPER_SUFFIXES:
            issues.append(
                Issue(
                    "error",
                    "desktop.wallpaper",
                    f"壁紙に使えない形式です: {candidate.suffix}",
                    hint="使える形式: " + ", ".join(WALLPAPER_SUFFIXES),
                )
            )
        if recipe.desktop.environment == "none":
            issues.append(
                Issue(
                    "warning",
                    "desktop.wallpaper",
                    "デスクトップ環境が none のため、壁紙は設定されません。",
                )
            )
        elif recipe.desktop.environment == "kde":
            issues.append(
                Issue(
                    "warning",
                    "desktop.wallpaper",
                    "KDE では壁紙の自動設定に対応していません。"
                    "画像はイメージ内にコピーされます。",
                    hint="KDE では手動で壁紙を設定してください。",
                )
            )

    seen_key_names: set[str] = set()
    seen_key_stems: set[str] = set()
    for key_path in recipe.build.repository_keys:
        candidate = recipe.resolve(key_path)
        if not candidate.is_file():
            issues.append(
                Issue(
                    "error",
                    "build.repository_keys",
                    f"リポジトリの鍵が見つかりません: {key_path}",
                    hint=f"探した場所: {candidate}",
                )
            )
            continue
        if not RE_KEYRING_NAME.match(candidate.name):
            issues.append(
                Issue(
                    "error",
                    "build.repository_keys",
                    f"鍵のファイル名に使えない文字があります: {candidate.name}",
                    hint="半角英数字・._- のみにしてください。",
                )
            )
        if candidate.suffix.lower() not in (".gpg", ".asc", ".pgp"):
            issues.append(
                Issue(
                    "error",
                    "build.repository_keys",
                    f"鍵の形式が不明です: {candidate.name}",
                    hint=".gpg / .asc / .pgp のいずれかにしてください。",
                )
            )
        if candidate.name in seen_key_names:
            issues.append(
                Issue(
                    "error",
                    "build.repository_keys",
                    f"同じ名前の鍵が複数あります: {candidate.name}",
                    hint="イメージ内で /usr/share/keyrings/ に同じ名前で置かれるためです。",
                )
            )
        if candidate.stem in seen_key_stems:
            issues.append(
                Issue(
                    "error",
                    "build.repository_keys",
                    f"同じベース名の鍵が複数あります: {candidate.stem}",
                    hint="拡張子を変えただけの同名ファイルは config/archives/ で衝突します。",
                )
            )
        seen_key_names.add(candidate.name)
        seen_key_stems.add(candidate.stem)


# --------------------------------------------------------------------------
# TOML 書き出し
# --------------------------------------------------------------------------


def dumps(data: dict[str, Any]) -> str:
    """辞書を TOML 文字列にする。

    TOML では 1 つのテーブル内で「素の値 → サブテーブル」の順に並んでいる
    必要があるので、挿入順を保ちつつその 2 グループに並べ替えて出力する。
    """
    lines: list[str] = []
    _emit_table(lines, (), data)
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip("\n") + "\n"


def _is_table(value: Any) -> bool:
    return isinstance(value, dict)


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, dict) for item in value
    )


def _emit_table(lines: list[str], path: tuple[str, ...], table: dict[str, Any]) -> None:
    scalars = [
        (key, value)
        for key, value in table.items()
        if not _is_table(value) and not _is_table_array(value)
    ]
    subtables = [(key, value) for key, value in table.items() if _is_table(value)]
    table_arrays = [
        (key, value) for key, value in table.items() if _is_table_array(value)
    ]

    if path:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{'.'.join(_quote_key(part) for part in path)}]")

    for key, value in scalars:
        lines.append(f"{_quote_key(key)} = {_toml_value(value)}")

    for key, value in subtables:
        _emit_table(lines, path + (key,), value)

    for key, values in table_arrays:
        full = path + (key,)
        name = ".".join(_quote_key(part) for part in full)
        for item in values:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[[{name}]]")
            scalars_inner = [
                (k, v)
                for k, v in item.items()
                if not _is_table(v) and not _is_table_array(v)
            ]
            for inner_key, inner_value in scalars_inner:
                lines.append(f"{_quote_key(inner_key)} = {_toml_value(inner_value)}")


def _quote_key(key: str) -> str:
    """必要ならベアキーを引用する。"""
    if re.match(r"^[A-Za-z0-9_-]+$", key):
        return key
    return _toml_basic_string(key)


def _clean(
    table: dict[str, Any], keep: tuple[str, ...] = ()
) -> dict[str, Any]:
    """未設定の項目を落として、出力をすっきりさせる。

    落とすのは空文字と空配列だけ。`0` や `false` は意味のある値なので残す。
    keep に書いたキーは、空でも意味があるので残す。
    """
    return {
        key: value
        for key, value in table.items()
        if key in keep
        or (value is not None and not (value == "" or value == []))
    }


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) == 1:
            return f"[{_toml_value(value[0])}]"
        body = "".join(f"    {_toml_value(item)},\n" for item in value)
        return "[\n" + body + "]"
    raise TypeError(f"TOML に書き出せない型です: {type(value).__name__}")


def _toml_string(value: str) -> str:
    """文字列を TOML にする。

    改行を含み、かつ ''' を含まない場合はリテラル複数行文字列にする。
    エスケープが要らないのでシェルスクリプトや設定ファイルの中身が
    そのまま読めて、生成物を目で確認しやすくなる。
    """
    if "\n" in value and "'''" not in value:
        body = value
        if body.startswith("\n"):
            # 開きデリミタ直後の改行は TOML が読み飛ばすので、1 つ足して相殺する
            body = "\n" + body
        return "'''\n" + body + "'''"
    return _toml_basic_string(value)


def _toml_basic_string(value: str) -> str:
    out = ['"']
    for char in value:
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)
