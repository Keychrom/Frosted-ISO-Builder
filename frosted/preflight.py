"""ビルドを始める前に環境を確認する。

ISO のビルドは失敗すると数十分が無駄になる。原因がレシピ側ではなく環境側に
あること (root じゃない、空き容量が足りない、ツールが無い) はよくあるので、
始める前に全部まとめて確認して、まとめて出す。

ここで見つけた問題を「対処法つき」で返すのがこのモジュールの役目。単に
「失敗しました」と言われても利用者は次に何をすればいいか分からない。
"""

from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .recipe import Recipe
from .runner import is_root, run_capture, which

#: これが無いと live-build はまず動かない。欠けていればエラー扱い。
MANDATORY_TOOLS: tuple[tuple[str, str], ...] = (
    ("lb", "live-build"),
    ("debootstrap", "debootstrap (Debian の最小システムを展開する)"),
    ("xorriso", "xorriso (ISO イメージを書き出す)"),
    ("mksquashfs", "squashfs-tools (ライブファイルシステムを作る)"),
    ("mount", "util-linux"),
    ("chroot", "coreutils"),
    ("cpio", "cpio (initramfs の展開に必要)"),
    ("rsync", "rsync"),
    ("uuidgen", "uuid-runtime (UUID の生成に必要)"),
)

#: 無くても警告で済ませるもの。用途によっては使わない。
OPTIONAL_TOOLS: tuple[tuple[str, str], ...] = (
    ("qemu-system-x86_64", "QEMU (frosted test で起動確認するときに使う)"),
    ("apt-cacher-ng", "apt-cacher-ng (再ビルド時のパッケージ取得を速くする)"),
    ("zsyncmake", "zsync (差分配布用の .zsync を作るときに使う)"),
)

#: 空き容量のしきい値 (GiB)
DISK_ERROR_GB = 6
DISK_WARN_GB = 20


@dataclass
class Check:
    """診断 1 項目の結果。"""

    name: str
    status: str  # "ok" | "warn" | "fail" | "skip"
    detail: str = ""
    hint: str = ""

    @property
    def is_failure(self) -> bool:
        return self.status == "fail"


@dataclass
class PreflightReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == "fail"]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == "warn"]

    @property
    def passed(self) -> bool:
        return not self.failures


def run(
    recipe: Recipe,
    *,
    require_root: bool = True,
    check_network: bool = True,
) -> PreflightReport:
    """環境を一式確認する。"""
    report = PreflightReport()
    report.checks.append(_check_platform())
    if require_root:
        report.checks.append(_check_root())
    report.checks.extend(_check_tools())
    report.checks.append(_check_architecture(recipe))
    report.checks.append(_check_disk(recipe))
    report.checks.append(_check_lb_options(recipe))
    if check_network:
        report.checks.append(_check_mirror(recipe))
    return report


# --------------------------------------------------------------------------
# 個別のチェック
# --------------------------------------------------------------------------


def _check_platform() -> Check:
    """Debian (またはその派生) の上で動いているか。"""
    release_file = Path("/etc/debian_version")
    if release_file.is_file():
        try:
            release = release_file.read_text(encoding="utf-8").strip()
        except OSError:
            release = ""
        return Check("OS", "ok", f"Debian {release}" if release else "Debian")

    os_release = Path("/etc/os-release")
    if os_release.is_file():
        try:
            text = os_release.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        name = ""
        for line in text.splitlines():
            if line.startswith("PRETTY_NAME="):
                name = line.split("=", 1)[1].strip().strip('"')
                break
        return Check(
            "OS",
            "warn",
            f"Debian ではありません: {name or '不明'}",
            hint="live-build は Debian 系を前提にしています。他のディストロでは動かない可能性があります。",
        )

    return Check(
        "OS",
        "skip",
        "/etc/os-release が読めません (Linux 以外で実行している可能性があります)",
    )


def _check_root() -> Check:
    if is_root():
        return Check("権限", "ok", "root で実行中")
    if os.name == "nt":  # 設定生成だけなら Windows でもできる
        return Check(
            "権限",
            "fail",
            "root ではありません",
            hint="ビルドは Debian 上で root として実行する必要があります。",
        )
    return Check(
        "権限",
        "fail",
        "root ではありません",
        hint="sudo を付けて実行してください: sudo frosted build <レシピ>",
    )


def _check_tools() -> list[Check]:
    checks: list[Check] = []
    missing_required: list[tuple[str, str]] = []
    for command, description in MANDATORY_TOOLS:
        if which(command) is None:
            missing_required.append((command, description))

    if missing_required:
        names = ", ".join(command for command, _ in missing_required)
        checks.append(
            Check(
                "必須ツール",
                "fail",
                f"見つかりません: {names}",
                hint=_apt_hint([command for command, _ in missing_required]),
            )
        )
    else:
        checks.append(
            Check("必須ツール", "ok", f"{len(MANDATORY_TOOLS)} 個すべて見つかりました")
        )

    missing_optional = [
        command for command, _ in OPTIONAL_TOOLS if which(command) is None
    ]
    if missing_optional:
        checks.append(
            Check(
                "任意ツール",
                "warn",
                f"見つかりません: {', '.join(missing_optional)}",
                hint="無くてもビルドできますが、あると便利です。",
            )
        )
    else:
        checks.append(Check("任意ツール", "ok", "すべて見つかりました"))

    return checks


def _apt_hint(packages: list[str]) -> str:
    # コマンド名とパッケージ名が違うものだけ手当てする
    mapping = {
        "lb": "live-build",
        "mksquashfs": "squashfs-tools",
        "uuidgen": "uuid-runtime",
        "cpio": "cpio",
        # コマンド名とパッケージ名が違うもの。chroot という名前の
        # パッケージは存在しない (coreutils に入っている)。
        "chroot": "coreutils",
        "mount": "util-linux",
    }
    resolved: list[str] = []
    for command in packages:
        package = mapping.get(command, command)
        if package not in resolved:
            resolved.append(package)
    return "次を実行してください: sudo apt install " + " ".join(sorted(resolved))


def _check_architecture(recipe: Recipe) -> Check:
    """ホストと違うアーキテクチャをビルドしようとしていないか。"""
    machine = os.uname().machine if hasattr(os, "uname") else ""
    normalized = {"x86_64": "amd64", "aarch64": "arm64", "i686": "i386"}.get(
        machine, machine
    )
    if not normalized:
        return Check("アーキテクチャ", "skip", "ホストの種類を判定できません")

    if normalized == recipe.iso.architecture:
        return Check(
            "アーキテクチャ", "ok", f"ホストと同じです: {recipe.iso.architecture}"
        )

    return Check(
        "アーキテクチャ",
        "warn",
        f"ホストは {normalized} ですが {recipe.iso.architecture} を作ろうとしています",
        hint="クロスビルドには qemu-user-static と binfmt の設定が必要で、"
        "とても遅くなります。同じアーキテクチャのマシンでビルドするのを勧めます。",
    )


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _check_disk(recipe: Recipe) -> Check:
    """作業ディレクトリに十分な空きがあるか。"""
    target = _existing_ancestor(recipe.workdir())
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return Check("空き容量", "skip", f"確認できません: {exc}")

    free_gb = usage.free / (1024**3)
    detail = f"{free_gb:.1f} GiB 空き ({target})"
    if free_gb < DISK_ERROR_GB:
        return Check(
            "空き容量",
            "fail",
            detail,
            hint=f"最低 {DISK_ERROR_GB} GiB、快適に作るなら {DISK_WARN_GB} GiB 以上必要です。",
        )
    if free_gb < DISK_WARN_GB:
        return Check(
            "空き容量",
            "warn",
            detail,
            hint=f"デスクトップ入りのイメージだと足りなくなることがあります。"
            f"{DISK_WARN_GB} GiB 以上を確保するのを勧めます。",
        )
    return Check("空き容量", "ok", detail)


def _check_lb_options(recipe: Recipe) -> Check:
    """これから渡す lb config のオプションを、実際の lb が受け付けるか確認する。

    live-build はオプション名がバージョンで揺れている (単数形/複数形) ので、
    実行前に突き合わせておく。ここで見つかれば、ビルドを走らせてから
    「オプションが不正」で落ちるのを避けられる。
    """
    from .backend.livebuild import build_lb_args, probe_option_spellings

    if which("lb") is None:
        return Check("lb オプション", "skip", "lb が見つからないため確認できません")

    spellings = probe_option_spellings(refresh=True)
    if not spellings.probed:
        return Check(
            "lb オプション",
            "skip",
            "`lb config --help` を読めませんでした",
            hint="既定の綴りで生成します。ビルドが通れば問題ありません。",
        )

    args, warnings = build_lb_args(recipe)
    flags = [arg for arg in args if arg.startswith("--")]
    if warnings:
        return Check(
            "lb オプション",
            "warn",
            "一部の設定が反映されません",
            hint=" / ".join(dict.fromkeys(warnings)),
        )
    return Check("lb オプション", "ok", f"{len(flags)} 個すべて対応しています")


def _check_mirror(recipe: Recipe) -> Check:
    """APT ミラーに到達できるか。プロキシ環境では落とせないので警告どまり。"""
    mirror = recipe.build.mirror.rstrip("/")
    if not mirror.startswith(("http://", "https://")):
        return Check("ミラー", "skip", f"URL ではないので確認を省略しました: {mirror}")

    url = f"{mirror}/dists/{recipe.iso.distribution}/Release"
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            if status == 200:
                return Check("ミラー", "ok", f"到達できます: {mirror}")
            return Check(
                "ミラー",
                "warn",
                f"HTTP {status} が返りました: {url}",
                hint="ミラーの URL か、そのディストリビューション名を確認してください。",
            )
    except urllib.error.HTTPError as exc:
        return Check(
            "ミラー",
            "fail",
            f"HTTP {exc.code} が返りました: {url}",
            hint=f"{recipe.iso.distribution} がそのミラーに存在するか確認してください。"
            " 社内ミラーを使っているなら build.mirror を書き換えてください。",
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Check(
            "ミラー",
            "warn",
            f"確認できませんでした: {exc}",
            hint="ネットワークが無い、またはプロキシが必要かもしれません。"
            " 社内ミラーを使うなら build.mirror を書き換えてください。",
        )
