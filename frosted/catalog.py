"""デスクトップ環境とプリセットのカタログ。

「どんな ISO が作れるか」の知識をここに集めておく。ウィザードはこの表を
そのまま選択肢として出し、バックエンドはここからパッケージ一覧を引く。
新しいデスクトップ環境やプリセットを足したいときは、このファイルだけを
触れば済むようにしている。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .i18n import t_block
from .recipe import Recipe, WriteEntry

# --------------------------------------------------------------------------
# デスクトップ環境
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DesktopProfile:
    key: str
    label: str
    description: str
    packages: tuple[str, ...] = ()
    #: ログイン画面を出すディスプレイマネージャ。空なら CUI のみ。
    display_manager: str = ""
    #: `x-session-manager=` ブートパラメータに渡す値
    x_session: str = ""
    #: 自動ログイン時に選ぶセッション名 (lightdm と sddm で使う)
    autologin_session: str = ""
    #: インストールに必要なディスク容量の目安 (MiB)。ウィザードの説明用。
    approx_size_mb: int = 0


DESKTOPS: dict[str, DesktopProfile] = {
    "none": DesktopProfile(
        key="none",
        label="なし (CUI)",
        description="X もデスクトップも入れない最小構成。レスキューやサーバー用途。",
        packages=(),
        approx_size_mb=350,
    ),
    "xfce": DesktopProfile(
        key="xfce",
        label="Xfce",
        description="軽くて安定。Live USB の定番。初めてならこれ。",
        packages=(
            "task-xfce-desktop",
            "lightdm",
            "lightdm-gtk-greeter",
            "xfce4-terminal",
            "xfce4-power-manager",
            "xfce4-notifyd",
        ),
        display_manager="lightdm",
        x_session="xfce4-session",
        autologin_session="xfce",
        approx_size_mb=1200,
    ),
    "lxqt": DesktopProfile(
        key="lxqt",
        label="LXQt",
        description="Xfce よりさらに軽い。古いマシンやキオスク向け。",
        packages=(
            "task-lxqt-desktop",
            "sddm",
        ),
        display_manager="sddm",
        x_session="startlxqt",
        autologin_session="lxqt",
        approx_size_mb=1100,
    ),
    "mate": DesktopProfile(
        key="mate",
        label="MATE",
        description="GNOME 2 の流れをくむ伝統的なデスクトップ。",
        packages=(
            "task-mate-desktop",
            "lightdm",
            "lightdm-gtk-greeter",
        ),
        display_manager="lightdm",
        x_session="mate-session",
        autologin_session="mate",
        approx_size_mb=2000,
    ),
    "gnome": DesktopProfile(
        key="gnome",
        label="GNOME",
        description="標準的で高機能。そのぶん重い (2GB 以上推奨)。",
        packages=(
            "task-gnome-desktop",
            "gdm3",
        ),
        display_manager="gdm3",
        x_session="gnome-session",
        autologin_session="",
        approx_size_mb=3000,
    ),
    "kde": DesktopProfile(
        key="kde",
        label="KDE Plasma",
        description="高機能で見た目も良い。重め。",
        packages=(
            "task-kde-desktop",
            "sddm",
        ),
        display_manager="sddm",
        x_session="plasma",
        autologin_session="plasma",
        approx_size_mb=3200,
    ),
    "cinnamon": DesktopProfile(
        key="cinnamon",
        label="Cinnamon",
        description="Windows に近い操作感。",
        packages=(
            "task-cinnamon-desktop",
            "lightdm",
            "lightdm-gtk-greeter",
        ),
        display_manager="lightdm",
        x_session="cinnamon-session",
        autologin_session="cinnamon",
        approx_size_mb=2200,
    ),
}


def desktop(key: str) -> DesktopProfile:
    """キーからデスクトップ定義を引く。知らなければ CUI 扱い。"""
    return DESKTOPS.get(key, DESKTOPS["none"])


# --------------------------------------------------------------------------
# 言語サポート
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguagePack:
    key: str
    label: str
    description: str
    packages: tuple[str, ...]


LANGUAGE_PACKS: dict[str, LanguagePack] = {
    "none": LanguagePack(
        key="none",
        label="追加なし",
        description="英語のみ。イメージが小さくなる。",
        packages=(),
    ),
    "ja": LanguagePack(
        key="ja",
        label="日本語",
        description="日本語フォント、かな漢字変換 (fcitx5 + mozc)、日本語ドキュメント。",
        packages=(
            "fonts-noto-cjk",
            "fonts-noto-color-emoji",
            "fonts-vlgothic",
            "fcitx5",
            "fcitx5-mozc",
            "fcitx5-frontend-gtk3",
            "fcitx5-frontend-gtk4",
            "fcitx5-frontend-qt5",
            "fcitx5-frontend-qt6",
            "im-config",
            "manpages-ja",
        ),
    ),
    "ko": LanguagePack(
        key="ko",
        label="韓国語",
        description="韓国語フォントと入力メソッド。",
        packages=(
            "fonts-noto-cjk",
            "fonts-nanum",
            "fcitx5",
            "fcitx5-hangul",
            "fcitx5-frontend-gtk3",
            "fcitx5-frontend-gtk4",
            "fcitx5-frontend-qt5",
            "fcitx5-frontend-qt6",
            "im-config",
            "manpages-ko",
        ),
    ),
    "zh": LanguagePack(
        key="zh",
        label="中国語",
        description="中国語フォントと入力メソッド。",
        packages=(
            "fonts-noto-cjk",
            "fcitx5",
            "fcitx5-chinese-addons",
            "fcitx5-frontend-gtk3",
            "fcitx5-frontend-gtk4",
            "fcitx5-frontend-qt5",
            "fcitx5-frontend-qt6",
            "im-config",
            "manpages-zh",
        ),
    ),
}


# --------------------------------------------------------------------------
# プリセット
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    description: str
    apply: Callable[[Recipe], None]
    #: ウィザードでプリセットを選んだあとに続けて聞く項目
    asks: tuple[str, ...] = field(default_factory=tuple)


# --- 各プリセットの中身 --------------------------------------------------

#: どのプリセットにも入れる基本セット。
#: locales / console-setup / keyboard-configuration は live-config が
#: ロケールとキーボードを設定するのに必要。
BASE_PACKAGES: tuple[str, ...] = (
    "sudo",
    "locales",
    "console-setup",
    "keyboard-configuration",
    "kbd",
    "ca-certificates",
    "apt-utils",
    "less",
    "nano",
    "htop",
    "iproute2",
    "iputils-ping",
    "net-tools",
    "curl",
    "wget",
    "rsync",
    "pciutils",
    "usbutils",
    "file",
    "bash-completion",
    "eject",
)

RESCUE_PACKAGES: tuple[str, ...] = (
    "testdisk",
    "gddrescue",
    "parted",
    "gdisk",
    "dosfstools",
    "ntfs-3g",
    "exfatprogs",
    "e2fsprogs",
    "xfsprogs",
    "btrfs-progs",
    "mdadm",
    "lvm2",
    "cryptsetup",
    "smartmontools",
    "hdparm",
    "dmidecode",
    "lshw",
    "nmap",
    "tcpdump",
    "screen",
    "tmux",
    "mc",
    "vim",
    "openssh-server",
    "squashfs-tools",
    "ddrescueview",
    "fdisk",
    "partclone",
    "sshfs",
    "unzip",
    "p7zip-full",
)

DEV_PACKAGES: tuple[str, ...] = (
    "build-essential",
    "git",
    "vim",
    "emacs-nox",
    "python3",
    "python3-pip",
    "python3-venv",
    "gdb",
    "strace",
    "ltrace",
    "cmake",
    "pkg-config",
    "shellcheck",
    "jq",
    "ripgrep",
    "fd-find",
    "tmux",
    "tree",
    "podman",
    "qemu-user-static",
)

DESKTOP_EXTRAS: tuple[str, ...] = (
    "firefox-esr",
    "libreoffice",
    "vlc",
    "evince",
    "gimp",
    "file-roller",
    "mousepad",
    "thunar",
    "galculator",
)

KIOSK_PACKAGES: tuple[str, ...] = (
    "chromium",
    "unclutter",
    "x11-xserver-utils",
    "xdotool",
    "xserver-xorg",
    "xserver-xorg-legacy",
    "xinit",
    "sudo",
)

#: キオスクの起動スクリプト。URL は /etc/kiosk-url から読む。
#: こうしておくと、レシピの files.write を 1 行変えるだけで行き先を差し替えられる。
KIOSK_URL_FILE = "/etc/kiosk-url"
KIOSK_LAUNCHER = "/usr/local/bin/start-kiosk"

KIOSK_START_SCRIPT = """#!/bin/sh
# キオスクモードで Chromium を起動する。URL は /etc/kiosk-url から読む。
URL="$(cat /etc/kiosk-url 2>/dev/null || true)"
if [ -z "$URL" ]; then
    URL="about:blank"
fi

# 画面の消灯とスクリーンセーバーを止める
xset s off
xset s noblank
xset -dpms

# マウスカーソルを一定時間で隠す
unclutter -idle 0.5 -root &

exec chromium \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-features=TranslateUI \\
    --no-first-run \\
    --password-store=basic \\
    "$URL"
"""

KIOSK_AUTOSTART = """[Desktop Entry]
Type=Application
Name=Kiosk
Comment=キオスクブラウザを自動起動する
Exec=/usr/local/bin/start-kiosk
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def _apply_minimal(recipe: Recipe) -> None:
    recipe.desktop.environment = "none"
    recipe.user.autologin = True
    recipe.user.sudo = True
    recipe.ssh.enable_server = False


def _apply_rescue(recipe: Recipe) -> None:
    recipe.desktop.environment = "none"
    recipe.user.autologin = True
    recipe.user.sudo = True
    recipe.ssh.enable_server = True
    recipe.packages.include = _merge(recipe.packages.include, RESCUE_PACKAGES)
    # レスキューメディアは書き込み可能なメモリ上で動かしたいので永続化を勧める
    recipe.boot.append = _merge_text(recipe.boot.append, "toram")


def _apply_desktop(recipe: Recipe) -> None:
    if recipe.desktop.environment in ("", "none"):
        recipe.desktop.environment = "xfce"
    recipe.user.autologin = True
    recipe.user.sudo = True
    recipe.packages.include = _merge(recipe.packages.include, DESKTOP_EXTRAS)


def _apply_kiosk(recipe: Recipe) -> None:
    if recipe.desktop.environment in ("", "none"):
        recipe.desktop.environment = "xfce"
    recipe.user.autologin = True
    # キオスク端末は利用者に root 権限を与えない
    recipe.user.sudo = False
    recipe.ssh.enable_server = False
    # 焼き込み後に変更されないよう、ホームは揮発のままにする
    recipe.packages.include = _merge(recipe.packages.include, KIOSK_PACKAGES)

    if not any(w.path == KIOSK_LAUNCHER for w in recipe.files.write):
        recipe.files.write.append(
            WriteEntry(
                path=KIOSK_LAUNCHER,
                content=t_block(KIOSK_START_SCRIPT),
                mode="0755",
                owner="root:root",
            )
        )
    if not any(w.path == KIOSK_AUTOSTART_PATH for w in recipe.files.write):
        recipe.files.write.append(
            WriteEntry(
                path=KIOSK_AUTOSTART_PATH,
                content=t_block(KIOSK_AUTOSTART),
                mode="0644",
                owner="root:root",
            )
        )
    if not any(w.path == KIOSK_URL_FILE for w in recipe.files.write):
        recipe.files.write.append(
            WriteEntry(
                path=KIOSK_URL_FILE,
                content="http://example.com\n",
                mode="0644",
                owner="root:root",
            )
        )


KIOSK_AUTOSTART_PATH = "/etc/xdg/autostart/00-kiosk.desktop"


def _apply_dev(recipe: Recipe) -> None:
    recipe.desktop.environment = "none"
    recipe.user.autologin = True
    recipe.user.sudo = True
    recipe.ssh.enable_server = True
    recipe.packages.include = _merge(recipe.packages.include, DEV_PACKAGES)


PRESETS: dict[str, Preset] = {
    "minimal": Preset(
        key="minimal",
        label="最小構成",
        description="CUI のみの素の Debian Live。まずはこれでビルドが通ることを確かめるのに向く。",
        apply=_apply_minimal,
    ),
    "rescue": Preset(
        key="rescue",
        label="レスキュー",
        description="ディスク復旧・診断ツール一式。SSH 有効。壊れたマシンの救出用。",
        apply=_apply_rescue,
    ),
    "desktop": Preset(
        key="desktop",
        label="デスクトップ",
        description="Xfce + Firefox + LibreOffice。普段使いの Live USB。",
        apply=_apply_desktop,
    ),
    "kiosk": Preset(
        key="kiosk",
        label="キオスク端末",
        description="起動すると自動ログインして全画面ブラウザが開く。受付端末や掲示用。",
        apply=_apply_kiosk,
    ),
    "dev": Preset(
        key="dev",
        label="開発環境",
        description="ビルドツール一式 + SSH。持ち運べる開発環境。",
        apply=_apply_dev,
    ),
}


def _merge(existing: list[str], extra: tuple[str, ...]) -> list[str]:
    """順序を保ったまま重複を除いて足す。"""
    seen = set(existing)
    result = list(existing)
    for item in extra:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _merge_text(existing: str, extra: str) -> str:
    if extra in existing.split():
        return existing
    return (existing + " " + extra).strip()


def apply_preset(recipe: Recipe, preset_key: str) -> None:
    """プリセットをレシピに適用する。知らないキーなら例外。"""
    preset = PRESETS.get(preset_key)
    if preset is None:
        raise KeyError(preset_key)
    preset.apply(recipe)


def base_packages() -> tuple[str, ...]:
    return BASE_PACKAGES
