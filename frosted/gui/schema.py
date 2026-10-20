"""Web UI のフォーム定義と画面文言。

ラベルは (日本語, English) の組で持つ。CLI の i18n とは別に、GUI の
項目名はここで完結させている。値の選択肢は recipe.py の定数を使い、
実装とずれないようにする。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog import DESKTOPS, PRESETS
from ..i18n import translate_to_english
from ..recipe import (
    KNOWN_ARCHITECTURES,
    KNOWN_BINARY_FILESYSTEMS,
    KNOWN_BINARY_IMAGES,
    KNOWN_BOOTLOADERS,
    KNOWN_CHECKSUMS,
    KNOWN_CHROOT_FILESYSTEMS,
    KNOWN_COMPRESSION,
    KNOWN_DEBCONF_FRONTENDS,
    KNOWN_DEBCONF_PRIORITIES,
    KNOWN_DISTRIBUTIONS,
    KNOWN_INITRAMFS,
    KNOWN_INITRAMFS_COMPRESSION,
    KNOWN_INITSYSTEMS,
    KNOWN_INSTALLER_TYPES,
    KNOWN_SECURE_BOOT,
    KNOWN_SQUASHFS_COMPRESSION,
)

Pair = tuple[str, str]


def pick(pair: Pair, lang: str) -> str:
    return pair[1] if lang == "en" else pair[0]


def localize(text: str, lang: str) -> str:
    """既存の i18n 辞書を使って、カタログ由来の文言を訳す。"""
    return text if lang == "ja" else translate_to_english(text)


@dataclass(frozen=True)
class Field:
    path: str
    label: Pair
    kind: str = "text"
    options: tuple[str, ...] = ()
    placeholder: str = ""
    help: Pair | None = None
    required: bool = False


@dataclass(frozen=True)
class Section:
    key: str
    label: Pair
    fields: tuple[Field, ...]


def _f(
    path: str,
    ja: str,
    en: str,
    kind: str = "text",
    *,
    options: tuple[str, ...] = (),
    placeholder: str = "",
    help_ja: str = "",
    help_en: str = "",
    required: bool = False,
) -> Field:
    help_pair = (help_ja, help_en) if help_ja or help_en else None
    return Field(path, (ja, en), kind, options, placeholder, help_pair, required)


SECTIONS: tuple[Section, ...] = (
    Section(
        "iso",
        ("ISO", "ISO"),
        (
            _f(
                "iso.name",
                "名前",
                "Name",
                placeholder="mylinux",
                help_ja="英小文字・数字・ハイフン。ラベルの元になります。",
                help_en="Lowercase letters, digits and hyphens. Used for the label.",
                required=True,
            ),
            _f("iso.version", "バージョン", "Version", placeholder="1.0"),
            _f("iso.label", "ボリュームラベル", "Volume label"),
            _f(
                "iso.distribution",
                "ベース",
                "Base release",
                "select",
                options=KNOWN_DISTRIBUTIONS,
            ),
            _f(
                "iso.architecture",
                "アーキテクチャ",
                "Architecture",
                "select",
                options=KNOWN_ARCHITECTURES,
            ),
            _f("iso.output", "出力ファイル名", "Output file name"),
            _f("iso.publisher", "発行元", "Publisher"),
            _f("iso.preparer", "作成者", "Preparer"),
            _f("iso.application", "アプリケーション ID", "Application ID"),
        ),
    ),
    Section(
        "system",
        ("システム", "System"),
        (
            _f("system.hostname", "ホスト名", "Hostname"),
            _f("system.locale", "ロケール", "Locale", placeholder="ja_JP.UTF-8"),
            _f("system.timezone", "タイムゾーン", "Timezone", placeholder="Asia/Tokyo"),
            _f(
                "system.keyboard_layout",
                "キーボード配列",
                "Keyboard layout",
                placeholder="jp",
            ),
            _f(
                "system.keyboard_variant",
                "キーボードバリアント",
                "Keyboard variant",
            ),
            _f("system.keyboard_model", "キーボードモデル", "Keyboard model"),
            _f(
                "system.utc",
                "ハードウェア時計を UTC で扱う",
                "Treat hardware clock as UTC",
                "bool",
            ),
        ),
    ),
    Section(
        "user",
        ("ユーザー", "User"),
        (
            _f("user.name", "ユーザー名", "Username", placeholder="user"),
            _f("user.fullname", "表示名", "Full name", placeholder="Live User"),
            _f(
                "user.password",
                "パスワード",
                "Password",
                "password",
                help_ja="$ で始まる値はハッシュとして扱います。",
                help_en="Values starting with $ are treated as hashes.",
            ),
            _f(
                "user.root_password",
                "root パスワード",
                "Root password",
                "password",
            ),
            _f(
                "user.default_groups",
                "追加グループ",
                "Extra groups",
                placeholder="sudo,dialout",
            ),
            _f("user.autologin", "自動ログイン", "Autologin", "bool"),
            _f("user.sudo", "sudo を許可", "Allow sudo", "bool"),
        ),
    ),
    Section(
        "desktop",
        ("デスクトップ", "Desktop"),
        (
            _f(
                "desktop.environment",
                "デスクトップ環境",
                "Desktop environment",
                "select",
                options=tuple(DESKTOPS),
            ),
            _f("desktop.session_manager", "セッションマネージャ", "Session manager"),
            _f(
                "desktop.extra_packages",
                "追加パッケージ",
                "Extra packages",
                "list",
            ),
            _f(
                "desktop.wallpaper",
                "壁紙",
                "Wallpaper",
                "path",
                placeholder="./assets/wallpaper.png",
            ),
        ),
    ),
    Section(
        "packages",
        ("パッケージ", "Packages"),
        (
            _f(
                "packages.include",
                "追加パッケージ",
                "Include packages",
                "list",
            ),
            _f(
                "packages.exclude",
                "削除パッケージ",
                "Exclude packages",
                "list",
            ),
            _f(
                "packages.local",
                "同梱する .deb",
                "Local .deb files",
                "list",
                help_ja="_all.deb または _<arch>.deb の名前にしてください。",
                help_en="File names must end in _all.deb or _<arch>.deb.",
            ),
            _f(
                "kernel.packages",
                "カーネルパッケージ",
                "Kernel package",
                placeholder="linux-image",
            ),
            _f(
                "kernel.flavours",
                "カーネルフレーバー",
                "Kernel flavours",
                "list",
            ),
        ),
    ),
    Section(
        "repositories",
        ("リポジトリ", "Repositories"),
        (
            _f("build.mirror", "Debian ミラー", "Debian mirror"),
            _f("build.security_mirror", "security ミラー", "Security mirror"),
            _f(
                "build.archive_areas",
                "アーカイブ領域",
                "Archive areas",
                "list",
                help_ja="main contrib non-free-firmware など。",
                help_en="For example main, contrib and non-free-firmware.",
            ),
            _f(
                "build.extra_repositories",
                "追加リポジトリ",
                "Extra repositories",
                "list",
                help_ja="1 行に 1 つの deb 行を書きます。",
                help_en="One deb line per line.",
            ),
            _f(
                "build.repository_keys",
                "GPG 鍵",
                "GPG keys",
                "list",
                help_ja="ホスト上の鍵ファイル。拡張子は .gpg/.asc/.pgp。",
                help_en="Key files on the host, ending in .gpg, .asc or .pgp.",
            ),
            _f(
                "build.repositories_in_image",
                "完成イメージにもリポジトリを残す",
                "Keep repositories in the image",
                "bool",
            ),
            _f("build.updates", "updates", "updates", "tristate"),
            _f("build.backports", "backports", "backports", "tristate"),
            _f(
                "build.proposed_updates",
                "proposed-updates",
                "proposed-updates",
                "tristate",
            ),
            _f("build.security", "security", "security", "tristate"),
            _f("build.source", "source イメージ", "Source images", "tristate"),
            _f(
                "apt.backend",
                "APT バックエンド",
                "APT backend",
                "select",
                options=("", "apt", "apt-get", "aptitude"),
            ),
            _f("apt.secure", "署名を検証", "Verify signatures", "tristate"),
            _f(
                "apt.source_archives",
                "deb-src を含める",
                "Include deb-src",
                "tristate",
            ),
            _f(
                "apt.indices",
                "パッケージインデックスを残す",
                "Keep package indices",
                "tristate",
            ),
            _f("apt.options", "APT オプション", "APT options"),
            _f("apt.pipeline", "パイプライン段数", "Pipeline depth", "int"),
            _f(
                "apt.keyring_packages",
                "鍵パッケージ",
                "Keyring packages",
                "list",
            ),
            _f(
                "apt.preferences",
                "ピン留め",
                "Pin preferences",
                "textarea",
            ),
        ),
    ),
    Section(
        "boot_image",
        ("ブートとイメージ", "Boot & image"),
        (
            _f(
                "boot.append",
                "起動パラメータ",
                "Live kernel parameters",
                placeholder="quiet splash",
            ),
            _f(
                "boot.install_append",
                "インストール先のパラメータ",
                "Installed system parameters",
                placeholder="quiet splash",
            ),
            _f("boot.persistence", "永続化", "Persistence", "bool"),
            _f(
                "boot.failsafe_noautologin",
                "failsafe で自動ログインを切る",
                "No autologin in failsafe",
                "bool",
            ),
            _f(
                "build.bootloaders",
                "ブートローダ",
                "Bootloaders",
                "list",
                help_ja="syslinux grub-efi など。",
                help_en="For example syslinux and grub-efi.",
            ),
            _f(
                "build.secure_boot",
                "Secure Boot",
                "Secure Boot",
                "select",
                options=KNOWN_SECURE_BOOT,
            ),
            _f("build.memtest", "memtest を入れる", "Include memtest", "bool"),
            _f(
                "binary.image_type",
                "イメージ種別",
                "Image type",
                "select",
                options=KNOWN_BINARY_IMAGES,
            ),
            _f(
                "binary.filesystem",
                "ファイルシステム",
                "Filesystem",
                "select",
                options=("",) + KNOWN_BINARY_FILESYSTEMS,
            ),
            _f(
                "binary.checksums",
                "チェックサム",
                "Checksums",
                "select",
                options=KNOWN_CHECKSUMS,
            ),
            _f(
                "binary.chroot_filesystem",
                "chroot ファイルシステム",
                "Chroot filesystem",
                "select",
                options=("",) + KNOWN_CHROOT_FILESYSTEMS,
            ),
            _f(
                "binary.squashfs_compression",
                "squashfs 圧縮",
                "Squashfs compression",
                "select",
                options=KNOWN_SQUASHFS_COMPRESSION,
            ),
            _f(
                "binary.squashfs_compression_level",
                "squashfs 圧縮レベル",
                "Squashfs compression level",
                "int",
            ),
            _f(
                "binary.initramfs_compression",
                "initramfs 圧縮",
                "Initramfs compression",
                "select",
                options=("",) + KNOWN_INITRAMFS_COMPRESSION,
            ),
            _f("binary.zsync", "zsync を作る", "Generate zsync", "tristate"),
            _f(
                "binary.win32_loader",
                "win32-loader",
                "win32-loader",
                "tristate",
            ),
            _f(
                "binary.swap_file_path",
                "スワップファイルのパス",
                "Swap file path",
                placeholder="/swapfile",
            ),
            _f(
                "binary.swap_file_size",
                "スワップサイズ (MB)",
                "Swap size (MB)",
                "int",
            ),
        ),
    ),
    Section(
        "installer",
        ("インストーラー", "Installer"),
        (
            _f(
                "installer.type",
                "インストーラー種別",
                "Installer type",
                "select",
                options=KNOWN_INSTALLER_TYPES,
            ),
            _f(
                "installer.gui",
                "グラフィカルインストーラー",
                "Graphical installer",
                "tristate",
            ),
            _f(
                "installer.distribution",
                "インストーラーのリリース",
                "Installer release",
            ),
            _f(
                "installer.preseed",
                "preseed ファイル",
                "Preseed file",
                "path",
            ),
            _f(
                "build.firmware_binary",
                "インストーラーにファームウェアを入れる",
                "Firmware in installer",
                "tristate",
            ),
        ),
    ),
    Section(
        "custom",
        ("SSH とスクリプト", "SSH & scripts"),
        (
            _f("ssh.enable_server", "SSH サーバー", "SSH server", "bool"),
            _f(
                "ssh.authorized_keys",
                "公開鍵",
                "Authorized keys",
                "list",
            ),
            _f(
                "ssh.permit_root_login",
                "root ログインを許可",
                "Allow root login",
                "bool",
            ),
            _f(
                "ssh.password_authentication",
                "パスワード認証",
                "Password authentication",
                "bool",
            ),
            _f(
                "scripts.setup",
                "ビルド時スクリプト",
                "Build-time scripts",
                "list",
            ),
            _f(
                "scripts.firstboot",
                "初回起動時スクリプト",
                "First-boot scripts",
                "list",
            ),
        ),
    ),
    Section(
        "build",
        ("ビルド", "Build"),
        (
            _f("build.workdir", "作業ディレクトリ", "Work directory"),
            _f("build.cache", "キャッシュを残す", "Keep cache", "bool"),
            _f(
                "build.compression",
                "アーカイブ圧縮",
                "Archive compression",
                "select",
                options=KNOWN_COMPRESSION,
            ),
            _f(
                "build.apt_recommends",
                "推奨パッケージを入れる",
                "Install recommended packages",
                "bool",
            ),
            _f("build.apt_proxy", "APT プロキシ", "APT proxy"),
            _f(
                "build.debootstrap_options",
                "debootstrap オプション",
                "debootstrap options",
            ),
            _f(
                "build.initsystem",
                "init システム",
                "Init system",
                "select",
                options=("",) + KNOWN_INITSYSTEMS,
            ),
            _f(
                "build.initramfs",
                "initramfs",
                "initramfs",
                "select",
                options=("",) + KNOWN_INITRAMFS,
            ),
            _f(
                "build.debconf_frontend",
                "debconf frontend",
                "debconf frontend",
                "select",
                options=("",) + KNOWN_DEBCONF_FRONTENDS,
            ),
            _f(
                "build.debconf_priority",
                "debconf priority",
                "debconf priority",
                "select",
                options=("",) + KNOWN_DEBCONF_PRIORITIES,
            ),
            _f(
                "build.firmware",
                "ファームウェアを入れる",
                "Include firmware",
                "bool",
            ),
        ),
    ),
)


UI_STRINGS: dict[str, Pair] = {
    "app_title": ("Frosted ISO Builder", "Frosted ISO Builder"),
    "recipe_path": ("レシピ", "Recipe"),
    "open": ("開く", "Open"),
    "new": ("新規", "New"),
    "save": ("保存", "Save"),
    "save_as": ("別名で保存", "Save as"),
    "generate": ("設定を生成", "Generate config"),
    "validate": ("検証", "Validate"),
    "doctor": ("環境診断", "Doctor"),
    "raw": ("TOML", "TOML"),
    "build": ("ビルド", "Build"),
    "commands": ("ビルド実行", "Build commands"),
    "copy": ("コピー", "Copy"),
    "copied": ("コピーしました", "Copied"),
    "unsaved": ("未保存の変更があります", "Unsaved changes"),
    "saved": ("保存しました", "Saved"),
    "save_failed": ("保存できませんでした", "Could not save"),
    "load_failed": ("読み込めませんでした", "Could not load"),
    "generated": ("設定を生成しました ({count} ファイル)", "Generated {count} files"),
    "validation_ok": ("問題ありません", "No problems"),
    "errors": ("エラー", "Errors"),
    "warnings_word": ("警告", "Warnings"),
    "no_issues": ("エラー・警告はありません", "No errors or warnings"),
    "summary": ("概要", "Summary"),
    "output": ("出力", "Output"),
    "workdir": ("作業ディレクトリ", "Work directory"),
    "base": ("ベース", "Base"),
    "desktop": ("デスクトップ", "Desktop"),
    "bootappend": ("ブートパラメータ", "Boot parameters"),
    "lb_args": ("lb config の引数", "lb config arguments"),
    "issues": ("検証結果", "Validation"),
    "close": ("閉じる", "Close"),
    "apply": ("適用", "Apply"),
    "cancel": ("キャンセル", "Cancel"),
    "new_title": ("新しいレシピ", "New recipe"),
    "name": ("名前", "Name"),
    "preset": ("プリセット", "Preset"),
    "none": ("なし", "None"),
    "unset": ("未指定", "Unset"),
    "yes": ("はい", "Yes"),
    "no": ("いいえ", "No"),
    "list_hint": ("1 行に 1 つ", "One per line"),
    "path_hint": ("レシピからの相対パス", "Relative to the recipe"),
    "build_help": (
        "ビルドは Debian 上で root 権限が必要です。",
        "Building requires Debian and root.",
    ),
    "build_command": ("ビルドコマンド", "Build command"),
    "test_command": ("起動確認コマンド", "Test command"),
    "doctor_network": ("ネットワークも確認", "Check network"),
    "doctor_help": (
        "ビルド環境を確認します。root 権限は不要です。",
        "Check the build environment. Root is not required.",
    ),
    "run_doctor": ("診断を実行", "Run doctor"),
    "raw_help": (
        "高度な設定は TOML で直接編集できます。保存するとコメントも保持されます。",
        "Edit advanced settings directly in TOML. Saving preserves comments.",
    ),
    "raw_stale": (
        "フォームの変更はまだ TOML に反映されていません。反映してから保存してください。",
        "Form changes are not in the TOML yet. Render them before saving.",
    ),
    "rendered": ("フォームの内容を TOML に反映しました", "Rendered the form to TOML"),
    "loaded_form": ("フォームに反映しました", "Loaded into the form"),
    "no_recipe": ("レシピが開かれていません", "No recipe is open"),
    "load_into_form": ("フォームに反映", "Load into form"),
    "save_raw": ("この内容で保存", "Save this TOML"),
    "form_toml": ("フォームの内容を TOML に反映", "Render form as TOML"),
    "generated_files": ("生成したファイル", "Generated files"),
    "open_recipe": ("レシピを開く", "Open recipe"),
    "unsaved_confirm": (
        "未保存の変更があります。破棄しますか?",
        "You have unsaved changes. Discard them?",
    ),
    "invalid_path": ("パスを確認してください", "Check the path"),
    "server_error": ("サーバーでエラーが発生しました", "Server error"),
    "network_error": ("サーバーに接続できません", "Cannot reach the server"),
    "loading": ("読み込み中...", "Loading..."),
    "saving": ("保存中...", "Saving..."),
    "validating": ("検証中...", "Validating..."),
    "generating": ("生成中...", "Generating..."),
    "doctor_running": ("診断中...", "Running doctor..."),
    "files_note": (
        "files.copy / files.write は TOML タブで編集してください。",
        "Edit files.copy / files.write in the TOML tab.",
    ),
    "backup": ("バックアップ: {path}", "Backup: {path}"),
    "preset_help": (
        "プリセットは新しいレシピの出発点です。",
        "Presets are starting points for a new recipe.",
    ),
    "build_note": (
        "GUI からのビルド実行は未対応です。コマンドをコピーして端末で実行してください。",
        "Building from the GUI is not supported yet. Copy the command and run it in a terminal.",
    ),
    "errors_count": ("{count} 件のエラー", "{count} errors"),
    "warnings_count": ("{count} 件の警告", "{count} warnings"),
    "error_one": ("1 件のエラー", "1 error"),
    "warning_one": ("1 件の警告", "1 warning"),
    "normalized_warning": (
        "フォームから保存すると TOML は正規化され、コメントは失われます。",
        "Saving from the form normalizes the TOML and loses comments.",
    ),
    "backup_created": ("バックアップを作成しました", "Backup created"),
}


def strings_for(lang: str) -> dict[str, str]:
    return {key: pick(pair, lang) for key, pair in UI_STRINGS.items()}


def schema_for(lang: str) -> list[dict]:
    sections: list[dict] = []
    for section in SECTIONS:
        fields: list[dict] = []
        for field in section.fields:
            if field.path == "desktop.environment":
                options = [
                    {
                        "value": key,
                        "label": localize(DESKTOPS[key].label, lang),
                    }
                    for key in field.options
                ]
            else:
                options = [
                    {"value": value, "label": value}
                    for value in field.options
                ]
            item = {
                "path": field.path,
                "label": pick(field.label, lang),
                "kind": field.kind,
                "options": options,
                "placeholder": field.placeholder,
                "help": pick(field.help, lang) if field.help else "",
                "required": field.required,
            }
            fields.append(item)
        sections.append(
            {
                "key": section.key,
                "label": pick(section.label, lang),
                "fields": fields,
            }
        )
    return sections


def presets_for(lang: str) -> list[dict]:
    return [
        {
            "key": key,
            "label": localize(preset.label, lang),
            "description": localize(preset.description, lang),
        }
        for key, preset in PRESETS.items()
    ]
