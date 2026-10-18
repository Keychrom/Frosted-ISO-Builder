"""対話形式でレシピを作るウィザード。

「簡単に使える」の実体はここ。live-build のオプションを一切知らなくても、
質問に答えていくだけでレシピが 1 枚できあがるようにしている。

既定値はホストの設定 (タイムゾーン・キーボード・ロケール) から拾う。
Debian マシンで走らせる前提なので、たいていは Enter だけで進める。
"""

from __future__ import annotations

import os
from pathlib import Path

from . import ui
from .catalog import DESKTOPS, LANGUAGE_PACKS, PRESETS, apply_preset
from .errors import UserAbort
from .i18n import get_language, t
from .recipe import (
    DEFAULT_MIRROR,
    KNOWN_ARCHITECTURES,
    KNOWN_COMPRESSION,
    RE_HOSTNAME,
    RE_ISO_NAME,
    RE_ISO_VERSION,
    RE_LOCALE,
    RE_TIMEZONE,
    RE_USERNAME,
    WALLPAPER_SUFFIXES,
    Recipe,
    WriteEntry,
)

#: キオスクの行き先を書き込むファイル (catalog と揃えてある)
KIOSK_URL_FILE = "/etc/kiosk-url"

#: ウィザードで選べる squashfs の圧縮方式。
#: live-build の --chroot-squashfs-compression-type が受け付ける値。
#: レシピの検証 (KNOWN_SQUASHFS_COMPRESSION) と揃えること。
SQUASHFS_COMPRESSION_CHOICES: tuple[tuple[str, str], ...] = (
    ("xz", "圧縮率が高い。ビルドは遅い。既定。"),
    ("zstd", "速くてそこそこ縮む。最近の傾向。"),
    ("gzip", "最速だが大きい。とにかく速く作りたいとき。"),
    ("lz4", "非常に速いが大きい。試行錯誤向け。"),
)


# --------------------------------------------------------------------------
# ホストの設定から既定値を拾う
# --------------------------------------------------------------------------


def _japanese_ui() -> bool:
    """UI が日本語かどうか。ホスト情報が無いときの既定値を選ぶのに使う。"""
    return get_language() == "ja"


def _host_timezone() -> str:
    for candidate in (Path("/etc/timezone"), Path("/var/db/zoneinfo")):
        try:
            if candidate.is_file():
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            continue
    return "Asia/Tokyo" if _japanese_ui() else "UTC"


def _host_keyboard() -> str:
    fallback = "jp" if _japanese_ui() else "us"
    try:
        text = Path("/etc/default/keyboard").read_text(encoding="utf-8")
    except OSError:
        return fallback
    for line in text.splitlines():
        if line.startswith("XKBLAYOUT="):
            value = line.split("=", 1)[1].strip().strip('"')
            if value:
                return value
    return fallback


def _host_locale() -> str:
    raw = os.environ.get("LANG") or os.environ.get("LC_ALL") or ""
    raw = raw.split(".")[0] if raw else ""
    if not raw or raw in ("C", "POSIX"):
        # ホストが C/POSIX なら、UI の言語に合わせて無難な既定値を選ぶ。
        # ここで常に ja_JP にすると、英語 UI の利用者に日本語ロケールを
        # 勧めてしまう。
        return "ja_JP.UTF-8" if _japanese_ui() else "C.UTF-8"
    # LANG の値に encoding が付いていなければ UTF-8 を補う
    lang = os.environ.get("LANG", "")
    if "." in lang:
        return lang
    return f"{raw}.UTF-8"


def _host_ssh_keys() -> list[str]:
    found: list[str] = []
    home = Path.home()
    for name in ("id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub"):
        candidate = home / ".ssh" / name
        if candidate.is_file():
            found.append(str(candidate))
    return found


# --------------------------------------------------------------------------
# 検証
# --------------------------------------------------------------------------


def _validate_iso_name(text: str) -> str | None:
    if not RE_ISO_NAME.match(text):
        return "半角小文字・数字・ハイフンのみ。先頭と末尾はハイフン以外。例: my-linux"
    return None


def _validate_username(text: str) -> str | None:
    if not RE_USERNAME.match(text):
        return "半角小文字で始まり、小文字・数字・_・- のみ (32 文字以内)。"
    if text == "root":
        return "root は使えません。"
    return None


def _validate_hostname(text: str) -> str | None:
    if not RE_HOSTNAME.match(text):
        return "半角小文字・数字・ハイフンのみ、63 文字以内。例: mylinux"
    return None


def _validate_version(text: str) -> str | None:
    if not RE_ISO_VERSION.match(text):
        return "半角英数字と . _ + ~ - のみ。空白や / は使えません。"
    return None


def _validate_wallpaper(text: str) -> str | None:
    path = Path(text).expanduser()
    if not path.is_file():
        return f"画像が見つかりません: {path}"
    if path.suffix.lower() not in WALLPAPER_SUFFIXES:
        return "使える形式: " + ", ".join(WALLPAPER_SUFFIXES)
    return None


def _validate_timezone(text: str) -> str | None:
    if not RE_TIMEZONE.match(text):
        return "例: Asia/Tokyo / Europe/Berlin / UTC"
    if hasattr(os, "uname") and not Path(f"/usr/share/zoneinfo/{text}").exists():
        return f"このマシンに /usr/share/zoneinfo/{text} がありません。綴りを確認してください。"
    return None


def _validate_locale(text: str) -> str | None:
    if not RE_LOCALE.match(text):
        return "例: ja_JP.UTF-8 / en_US.UTF-8 / C.UTF-8"
    return None


# --------------------------------------------------------------------------
# ウィザード本体
# --------------------------------------------------------------------------


def run(
    *,
    preset_key: str | None = None,
    name: str | None = None,
    distribution: str | None = None,
    architecture: str | None = None,
) -> Recipe:
    """対話でレシピを組み立てる。

    引数で渡された項目は質問を飛ばす (CLI オプションからの指定)。
    """
    ui.header("Linux ISO Builder — 新しいレシピを作る")
    ui.out("質問に答えていくと、ビルド用のレシピファイルが 1 枚できます。")
    ui.out(
        t(
            "括弧内が既定値です。そのまま使うなら {key} を押してください。",
            key=ui.bold("Enter"),
        )
    )
    ui.out(t("いつでも {key} で中断できます。", key=ui.bold("Ctrl-C")))

    recipe = Recipe()

    # --- 1. 名前 ---------------------------------------------------------
    ui.step("1/8  ISO の名前")
    recipe.iso.name = name or ui.ask(
        "名前 (英小文字・ハイフン)", default="mylinux", validate=_validate_iso_name
    )
    recipe.iso.version = ui.ask(
        "バージョン (ファイル名に入ります)",
        default="1.0",
        validate=_validate_version,
    )

    # --- 2. ベース -------------------------------------------------------
    ui.step("2/8  ベースにする Debian")
    recipe.iso.distribution = distribution or ui.ask_choice(
        "どのリリースをベースにしますか?",
        [
            ("trixie", "Debian 13。現行の安定版。特におすすめ。"),
            ("bookworm", "Debian 12。少し前の安定版。古いドライバが必要なとき。"),
            (
                "testing",
                "Debian Testing。次の安定版の開発版。新しいパッケージが使えるが、壊れることがある。",
            ),
            (
                "sid",
                "Debian Sid (unstable)。最先端だが動作保証はない。security ミラーは使わない。",
            ),
        ],
        default_index=0,
    )
    recipe.iso.architecture = architecture or ui.ask_choice(
        "アーキテクチャ",
        [
            ("amd64", "64bit PC。通常はこれ。"),
            ("i386", "32bit PC。よほど古いマシンでない限り不要。"),
            ("arm64", "64bit ARM。Raspberry Pi 4 以降など。"),
        ],
        default_index=0,
    )

    # --- 3. 用途 ---------------------------------------------------------
    ui.step("3/8  用途")
    if preset_key is None:
        preset_key = ui.ask_choice(
            "どんな用途の ISO にしますか?",
            [(key, p.description) for key, p in PRESETS.items()],
            default_index=0,
        )
    elif preset_key not in PRESETS:
        raise UserAbort(
            f"知らないプリセットです: {preset_key} "
            f"(選べるもの: {', '.join(PRESETS)})"
        )

    apply_preset(recipe, preset_key)
    ui.ok(
        t(
            "プリセット「{name}」を適用しました。",
            name=t(PRESETS[preset_key].label),
        )
    )

    # --- 4. デスクトップ環境 ---------------------------------------------
    ui.step("4/8  デスクトップ環境")
    desktop_keys = list(DESKTOPS)
    default_index = desktop_keys.index(recipe.desktop.environment) if recipe.desktop.environment in desktop_keys else 0
    chosen = ui.ask_choice(
        "デスクトップ環境",
        [(key, profile.description) for key, profile in DESKTOPS.items()],
        default_index=default_index,
    )
    recipe.desktop.environment = chosen

    profile = DESKTOPS[chosen]
    if profile.approx_size_mb:
        ui.info(t("イメージの大きさの目安: 約 {size} MB", size=profile.approx_size_mb))

    # --- 5. 言語 ---------------------------------------------------------
    ui.step("5/8  言語サポート")
    language_keys = list(LANGUAGE_PACKS)
    if chosen == "none":
        # CUI だけの構成にフォントや入力メソッドを入れても使い道がない
        guessed = "none"
    elif recipe.system.locale.startswith("ja") or _host_locale().startswith("ja"):
        guessed = "ja"
    else:
        guessed = "none"
    guessed_index = language_keys.index(guessed) if guessed in language_keys else 0
    chosen_language = ui.ask_choice(
        "追加の言語サポート",
        [(key, pack.description) for key, pack in LANGUAGE_PACKS.items()],
        default_index=guessed_index,
    )
    language = LANGUAGE_PACKS[chosen_language]

    preset_packages = list(recipe.packages.include)
    if language.packages:
        preset_packages.extend(language.packages)
        recipe.packages.include = preset_packages

    # --- 6. ユーザー -----------------------------------------------------
    ui.step("6/8  ユーザーとログイン")
    recipe.user.name = ui.ask(
        "ライブ環境のユーザー名", default="user", validate=_validate_username
    )
    recipe.user.fullname = ui.ask("フルネーム (表示用)", default="Live User")

    # 既定値はプリセットが決めた値にする。ここで True を既定にしてしまうと、
    # キオスクのように「sudo を与えない」と決めているプリセットの意図が
    # Enter を押しただけで消えてしまう。
    recipe.user.autologin = ui.ask_bool(
        "起動時に自動でログインしますか?", default=recipe.user.autologin
    )
    if not recipe.user.autologin:
        recipe.user.password = ui.ask_password(
            "パスワード (空のままにするとログインできません)"
        )
    elif recipe.user.password:
        ui.info("パスワードも設定済みです (SSH やコンソールログインで使えます)。")
    else:
        ui.info("自動ログインなのでパスワードは設定しません。")

    recipe.user.sudo = ui.ask_bool(
        "このユーザーに sudo (管理者権限) を許可しますか?",
        default=recipe.user.sudo,
    )

    # --- 7. 地域と言語の設定 ---------------------------------------------
    ui.step("7/8  地域の設定")
    recipe.system.hostname = ui.ask(
        "ホスト名", default=recipe.iso.name, validate=_validate_hostname
    )
    recipe.system.locale = ui.ask(
        "ロケール", default=_host_locale(), validate=_validate_locale
    )
    recipe.system.timezone = ui.ask(
        "タイムゾーン", default=_host_timezone(), validate=_validate_timezone
    )
    recipe.system.keyboard_layout = ui.ask(
        "キーボード配列", default=_host_keyboard()
    )

    # --- 8. 追加の設定 ---------------------------------------------------
    ui.step("8/8  追加の設定")
    extra = ui.ask_list(
        "追加で入れたいパッケージ (空白区切り、無ければ Enter)", default=[]
    )
    if extra:
        recipe.packages.include = list(recipe.packages.include) + [
            name for name in extra if name not in recipe.packages.include
        ]

    if not recipe.ssh.enable_server:
        recipe.ssh.enable_server = ui.ask_bool(
            "SSH サーバーを入れて、外からログインできるようにしますか?", default=False
        )
    if recipe.ssh.enable_server:
        default_keys = _host_ssh_keys()
        keys = ui.ask_list(
            "SSH 公開鍵のファイル (空白区切り)",
            default=default_keys,
        )
        recipe.ssh.authorized_keys = keys
        if not keys:
            ui.warn(
                "公開鍵を指定していません。パスワード認証は既定で無効なので、"
                "このままだと SSH でログインできません。"
            )
            recipe.ssh.password_authentication = ui.ask_bool(
                "パスワードでの SSH ログインを許可しますか?", default=True
            )

    if ui.ask_bool("詳細設定 (ミラー・圧縮方式・永続化) を変更しますか?", default=False):
        _ask_advanced(recipe)

    if preset_key == "kiosk":
        _ask_kiosk_url(recipe)

    return recipe


def _ask_advanced(recipe: Recipe) -> None:
    """上級者向けの設定。既定のままで困らないことがほとんど。"""
    recipe.build.mirror = ui.ask(
        "APT ミラー",
        default=recipe.build.mirror or DEFAULT_MIRROR,
    )
    recipe.binary.squashfs_compression = ui.ask_choice(
        "squashfs の圧縮方式",
        SQUASHFS_COMPRESSION_CHOICES,
        default_index=0,
    )
    wallpaper = ui.ask(
        "壁紙の画像 (空なら変更しない)",
        default=recipe.desktop.wallpaper or None,
        validate=_validate_wallpaper,
        allow_empty=True,
    ).strip()
    if wallpaper:
        recipe.desktop.wallpaper = str(Path(wallpaper).expanduser().resolve())
    recipe.build.cache = ui.ask_bool(
        "ビルドキャッシュを残しますか? (2 回目以降が速くなります)", default=True
    )
    recipe.boot.persistence = ui.ask_bool(
        "永続化 (persistence) を有効にしますか? "
        "USB に変更を保存できますが、USB 側の準備が別途必要です。",
        default=False,
    )


def _ask_kiosk_url(recipe: Recipe) -> None:
    """キオスクの行き先を聞いてレシピに埋め込む。"""
    url = ui.ask("キオスクで表示する URL", default="http://example.com")
    if not url:
        return
    for entry in recipe.files.write:
        if entry.path == KIOSK_URL_FILE:
            entry.content = url.rstrip("\n") + "\n"
            break
    else:
        recipe.files.write.append(
            WriteEntry(
                path=KIOSK_URL_FILE,
                content=url.rstrip("\n") + "\n",
                mode="0644",
                owner="root:root",
            )
        )
    ui.ok(f"起動時に {url} を全画面で開きます。")


# --------------------------------------------------------------------------
# 確認と保存
# --------------------------------------------------------------------------


def summarize(recipe: Recipe) -> list[tuple[str, str]]:
    """最終確認用の要約。(項目, 値) の並びを返す。

    ここで訳したものを返す。呼び出し側 (CLI) は行を組み立てるだけにして、
    表示のたびに訳し忘れが起きないようにしている。
    """
    profile = DESKTOPS.get(recipe.desktop.environment)
    rows = [
        (t("名前"), f"{recipe.iso.name} {recipe.iso.version}"),
        (t("出力ファイル"), recipe.iso.resolved_output()),
        (t("ベース"), f"Debian {recipe.iso.distribution} / {recipe.iso.architecture}"),
        (t("デスクトップ"), t(profile.label) if profile else recipe.desktop.environment),
        (t("ユーザー"), f"{recipe.user.name} ({recipe.user.fullname})"),
        (
            t("ログイン"),
            t("自動ログインあり") if recipe.user.autologin else t("パスワード入力"),
        ),
        (t("sudo"), t("あり") if recipe.user.sudo else t("なし")),
        (t("ホスト名"), recipe.system.resolved_hostname()),
        (t("ロケール"), recipe.system.locale),
        (t("タイムゾーン"), recipe.system.timezone),
        (t("キーボード"), recipe.system.keyboard_layout),
        (t("追加パッケージ"), t("{count} 個", count=len(recipe.packages.include))),
        (t("SSH"), t("有効") if recipe.ssh.enable_server else t("無効")),
        (t("作業ディレクトリ"), str(recipe.workdir())),
    ]
    if recipe.desktop.wallpaper:
        rows.append((t("壁紙"), recipe.desktop.wallpaper))
    if recipe.build.repository_keys:
        rows.append(
            (
                t("リポジトリの鍵"),
                t("{count} 個", count=len(recipe.build.repository_keys)),
            )
        )
    if recipe.boot.persistence:
        rows.append((t("永続化"), t("有効")))
    return rows


def confirm(recipe: Recipe) -> bool:
    """内容を見せて実行してよいか確認する。"""
    ui.header("この内容で作ります")
    label_width = max(len(label) for label, _ in summarize(recipe))
    for label, value in summarize(recipe):
        ui.out(f"  {label.ljust(label_width)}  {value}")
    ui.out()
    return ui.ask_bool("この内容でレシピを保存しますか?", default=True)


def suggest_path(recipe: Recipe, directory: Path | None = None) -> Path:
    base = directory or Path.cwd()
    return base / f"{recipe.iso.name}.toml"
