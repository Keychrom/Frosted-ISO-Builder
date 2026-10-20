# 機能一覧と使い方

[English](FEATURES.md) | **日本語**

Frosted ISO Builder は Debian Live ISO を TOML レシピ 1 枚から作るツールです。
この文書は「何ができるか」と「どう使うか」を用途ごとにまとめたものです。
全キーの既定値と細かい制約は [README.ja.md](README.ja.md) の
「レシピのリファレンス」を参照してください。

- [5 分で試す](#5-分で試す)
- [ブラウザ GUI](#ブラウザ-gui)
- [機能マップ](#機能マップ)
- [ISO の基本情報](#iso-の基本情報)
- [地域・言語・ユーザー](#地域言語ユーザー)
- [デスクトップ環境](#デスクトップ環境)
- [パッケージ](#パッケージ)
- [独自リポジトリと APT](#独自リポジトリと-apt)
- [ブートと永続化](#ブートと永続化)
- [イメージ構成と圧縮](#イメージ構成と圧縮)
- [Debian インストーラー](#debian-インストーラー)
- [ファイル・スクリプト・SSH](#ファイルスクリプトssh)
- [ビルド環境](#ビルド環境)
- [配布と検証](#配布と検証)
- [プリセット](#プリセット)
- [コマンド早見表](#コマンド早見表)
- [レシピ例](#レシピ例)
- [まだ設定できないもの・注意](#まだ設定できないもの注意)

---

## 5 分で試す

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder
sudo ./install.sh --with-deps

# 最小構成のレシピを作る (対話)
frosted init --preset minimal --name mylinux

# 環境とレシピを確認する
frosted doctor mylinux.toml
frosted validate mylinux.toml

# ビルドして QEMU で起動確認する
sudo frosted build mylinux.toml
frosted test mylinux.toml
```

対話を使わず、最小の TOML を直接書いても始められます。

```toml
version = 1

[iso]
name = "mylinux"
```

この状態でもビルドできます。あとは必要な項目を足していくだけです。
設定だけ生成して中身を確認したいときは `frosted gen mylinux.toml`
（root 不要）、live-build を直接叩きたいときは生成された `build/` で
`sudo lb build` を実行します（`auto/config` が自動で読まれます）。

## ブラウザ GUI

TOML を手で書かずに編集したいときは、ローカル Web UI を使えます。

```sh
# 既存のレシピを開く
frosted gui mylinux.toml

# 新規レシピから始める
frosted gui
```

`127.0.0.1` にだけ待ち受け、ブラウザが自動で開きます。別のサーバーが
ポートを使っている場合は、空いているポートへ自動で移ります。

画面では次のことができます。

- ISO・システム・ユーザー・デスクトップ・パッケージ・リポジトリ・
  ブート/イメージ・インストーラー・SSH/スクリプト・ビルドの設定を
  フォームで編集する
- 入力しながら検証し、エラーと警告を項目ごとに表示する
- `lb config` に渡る引数、ブートパラメータ、出力ファイル名を確認する
- レシピを保存する (既存ファイルは `.bak` にバックアップ)
- `frosted gen` 相当の設定生成と、`frosted doctor` 相当の環境診断
- TOML を直接編集する。こちらから保存するとコメントも保持される
- ビルド用の `sudo frosted build ...` コマンドを表示・コピーする

ビルド自体は GUI から実行しません。root 権限と Debian が必要なので、
表示されたコマンドを端末で実行してください。

フォームから保存すると TOML は正規化され、コメントは失われます。
コメントを残したいときは TOML タブで編集して保存してください。
`files.copy` / `files.write` のような配列設定も TOML タブで編集します。

GUI は `127.0.0.1` にだけバインドし、起動ごとのランダムなトークンと
Host ヘッダの検証で、他の Web サイトからの操作を防いでいます。
`--no-browser` でブラウザを開かずに起動でき、`--port` でポートを指定できます。

GUI は Windows / macOS でも編集・検証・生成に使えます。ISO のビルドだけは
Debian マシンで実行してください。

## 機能マップ

| カテゴリ | できること | 主な設定 |
| --- | --- | --- |
| ISO の基本 | 名前・版・ラベル・ベース・アーキテクチャ・出力名 | `[iso]` |
| 地域と言語 | ホスト名・ロケール・タイムゾーン・キーボード | `[system]` |
| ユーザー | ユーザー名・表示名・パスワード・sudo・自動ログイン | `[user]` |
| デスクトップ | 7 種類の環境・壁紙・追加パッケージ | `[desktop]` |
| パッケージ | 追加・除外・ローカル `.deb` の同梱・カーネル選択 | `[packages]`, `[kernel]` |
| リポジトリ | 独自ミラー・GPG 鍵・APT のピン留め | `[build]`, `[apt]` |
| ブート | カーネルパラメータ・永続化・ブートローダ・Secure Boot | `[boot]`, `[build]` |
| イメージ | 種別・ファイルシステム・圧縮・チェックサム・スワップ | `[binary]` |
| インストーラー | Debian インストーラーの同梱と preseed | `[installer]` |
| ファイル | ホストのファイルを入れる・中身を直接書く | `[[files.copy]]`, `[[files.write]]` |
| スクリプト | ビルド時フック・初回起動時フック | `[scripts]` |
| SSH | サーバー有効化・公開鍵・root ログイン | `[ssh]` |
| ビルド | 作業ディレクトリ・キャッシュ・ミラー・debconf | `[build]` |
| 配布 | SHA256・ビルド情報・GPG 署名・検証 | `build`, `verify` |
| 再現性 | プリセット・対話ウィザード・`show` での確認 | `init`, `presets` |

## ISO の基本情報

```toml
[iso]
name = "mycompany-live"       # 必須。英小文字・数字・ハイフン
version = "2026.10"
label = "MYCOMPANY_LIVE"      # 省略時は名前から生成
distribution = "trixie"       # bookworm / testing / sid も可
architecture = "amd64"        # amd64 / i386 / arm64
publisher = "Example Inc."
preparer = "Example Inc."
application = "MyCompany Live"
```

| キー | 説明 |
| --- | --- |
| `name` | ISO の名前。ラベルの生成に使われる (ウィザードではホスト名の既定値にもなる) |
| `version` | 出力ファイル名に入る版 |
| `label` | ISO のボリュームラベル (32 文字以内) |
| `distribution` | `trixie` / `bookworm` / `testing` / `forky` / `sid` / `unstable` |
| `architecture` | `amd64` / `i386` / `arm64` |
| `output` | 出力ファイル名。既定は `<名前>-<版>-<arch>.iso` |
| `publisher` / `preparer` | ISO に記録する発行元と作成者。配布するなら必ず設定する |
| `application` | ISO のアプリケーション識別子。既定は `name` |

`testing` と `sid` は開発版です。`sid` には security アーカイブが無いため、
`[build] security_mirror` は無視されます。

## 地域・言語・ユーザー

```toml
[system]
hostname = "mylinux"
locale = "ja_JP.UTF-8"
timezone = "Asia/Tokyo"
keyboard_layout = "jp"
keyboard_variant = ""
keyboard_model = ""
utc = true

[user]
name = "live"
fullname = "Live User"
password = "live"              # 平文。$6$... を書くとハッシュ扱い
root_password = ""
default_groups = "sudo,dialout"
autologin = true
sudo = true
```

| セクション | 主なキー |
| --- | --- |
| `[system]` | `hostname` / `locale` / `timezone` / `keyboard_layout` / `keyboard_variant` / `keyboard_model` / `utc` |
| `[user]` | `name` / `fullname` / `password` / `root_password` / `default_groups` / `autologin` / `sudo` |

ロケール・タイムゾーン・キーボード・ユーザー名・ホスト名・デスクトップの
セッションは、起動時に live-config へ渡されます。`fullname` はカーネル
パラメータではなく、起動後のセットアップで設定されます。

自動ログインを無効にした場合は `password` を設定してください。パスワードも
鍵も無いとログインできない組み合わせは、検証時に警告が出ます。

## デスクトップ環境

```toml
[desktop]
environment = "xfce"                       # none / xfce / lxqt / mate / gnome / kde / cinnamon
session_manager = ""                       # 通常は自動
extra_packages = ["fcitx5", "fcitx5-mozc"] # 環境に関係なく追加
wallpaper = "./assets/wallpaper.png"       # PNG / JPEG / WebP / SVG
```

| `environment` | 特徴 |
| --- | --- |
| `none` | CUI のみ。レスキューやサーバー用途 |
| `xfce` | 軽くて安定。Live USB の定番 |
| `lxqt` | Xfce よりさらに軽い |
| `mate` | 伝統的なデスクトップ |
| `gnome` | 高機能。2 GB 以上のメモリ推奨 |
| `kde` | 高機能で見た目も良い。重め |
| `cinnamon` | Windows に近い操作感 |

壁紙は Xfce / GNOME / MATE / Cinnamon / LXQt ではログイン時に自動設定されます。
KDE は自動設定に未対応で、画像がイメージ内にコピーされるだけです。

日本語・韓国語・中国語のフォントと入力メソッドは、`frosted init` の
ウィザードで言語を選ぶと `[packages] include` に追加されます。手書きの場合は
必要なパッケージを `extra_packages` か `[packages] include` に入れてください。
`extra_packages` は `environment = "none"` でも有効です。

## パッケージ

```toml
[packages]
include = ["vim", "curl", "git"]
exclude = ["nano"]
local = [
  "./debs/myapp_1.2.0_amd64.deb",
  "./debs/myapp-data_1.2.0_all.deb",
]

[kernel]
packages = "linux-image"     # 省略時は live-build の既定
flavours = ["amd64"]
```

| キー | 説明 |
| --- | --- |
| `include` | 追加で入れるパッケージ |
| `exclude` | インストール後に明示的に削除するパッケージ |
| `local` | ホスト上の `.deb`。`config/packages.chroot/` から依存関係ごと導入 |
| `[kernel] packages` / `flavours` | カーネルパッケージとフレーバー |

`exclude` は依存関係をたどらず、名指ししたパッケージだけを削除します。

`local` のファイル名は dpkg が付ける `_all.deb` または
`_<アーキテクチャ>.deb` のままにしてください。live-build はそれ以外の
名前を拾わないため、検証でエラーにしています。アーキテクチャ付きの
ファイルは `[iso] architecture` と一致している必要があります。

## 独自リポジトリと APT

```toml
[build]
mirror = "http://deb.debian.org/debian/"
security_mirror = "http://security.debian.org/debian-security/"
archive_areas = ["main", "contrib", "non-free-firmware"]
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://repo.example.com/debian trixie main",
]
repository_keys = ["./assets/myrepo.gpg"]
repositories_in_image = true
updates = true
backports = false

[apt]
backend = "apt"
options = "--no-install-recommends"
indices = false
preferences = '''
Package: *
Pin: release a=trixie
Pin-Priority: 100
'''
```

| 設定 | 説明 |
| --- | --- |
| `[build] mirror` | ベースにする Debian ミラー |
| `security_mirror` | security 更新のミラー。`sid`/`unstable` では無視 |
| `archive_areas` | `main` / `contrib` / `non-free` / `non-free-firmware` |
| `extra_repositories` | 追加リポジトリ。`deb ...` の行をそのまま書く |
| `repository_keys` | リポジトリの GPG 鍵。apt と `/usr/share/keyrings/` に配置 |
| `repositories_in_image` | `false` ならビルド時だけ。`true` なら完成イメージにも残す |
| `[apt] backend` | `apt` / `apt-get` / `aptitude` |
| `[apt] preferences` | APT のピン留め。`/etc/apt/preferences.d/frosted.pref` に入る |
| `[build] updates` etc. | updates / backports / proposed-updates / security / source |

追加リポジトリは既定ではパッケージ導入時だけ使われ、完成イメージの
`sources.list.d` からは外れます。ライブ環境でも `apt` でそのミラーを
使いたいときは `repositories_in_image = true` にしてください。

`signed-by=` を使う場合は、鍵を `repository_keys` に入れておけば
`/usr/share/keyrings/` に残ります。

## ブートと永続化

```toml
[boot]
append = "quiet splash"
install_append = "quiet splash"
persistence = true
failsafe_noautologin = true

[build]
bootloaders = ["syslinux", "grub-efi"]
secure_boot = "auto"
memtest = false
```

| キー | 説明 |
| --- | --- |
| `[boot] append` | ライブ起動時の追加カーネルパラメータ |
| `[boot] install_append` | インストーラーで導入したシステム向けのパラメータ |
| `[boot] persistence` | 永続化を有効にする |
| `[boot] failsafe_noautologin` | failsafe メニューで自動ログインを切る |
| `[build] bootloaders` | `syslinux` / `grub-efi` / `grub-pc` / `grub-legacy` |
| `[build] secure_boot` | `auto` / `enable` / `disable` |
| `[build] memtest` | memtest86+ のエントリを入れる |

ロケール・キーボード・ユーザー名などは自動でブートパラメータに組み込まれます。
`append` には `toram` や `quiet` など、live-boot に渡したいものを書きます。

arm64 では x86 用の `syslinux` / `grub-pc` / `grub-legacy` は使えず、
`grub-efi` のみになります。

永続化を使う場合、USB 側に `persistence` ラベルのパーティションと、
その直下の `persistence.conf` が別途必要です。イメージに含まれるのは
起動オプションだけです。

## イメージ構成と圧縮

```toml
[binary]
image_type = "iso-hybrid"          # iso / iso-hybrid / netboot / tar / hdd
filesystem = ""                     # hdd 用: fat32 / ext4 など
checksums = "sha256"
chroot_filesystem = "squashfs"
squashfs_compression = "zstd"
squashfs_compression_level = 19
initramfs_compression = "gzip"
zsync = true
win32_loader = false
swap_file_path = "/swapfile"
swap_file_size = 1024
```

| キー | 説明 |
| --- | --- |
| `image_type` | 通常は `iso-hybrid`。BIOS/UEFI 両対応で USB にも書ける |
| `filesystem` | hdd イメージのファイルシステム |
| `checksums` | `md5` / `sha1` / `sha256` / `sha512` / `none` など |
| `chroot_filesystem` | ライブファイルシステムの形式。通常は `squashfs` |
| `squashfs_compression` | `xz` / `zstd` / `gzip` / `lz4` など |
| `squashfs_compression_level` | mksquashfs の圧縮レベル |
| `initramfs_compression` | `bzip2` / `gzip` / `lzma` |
| `zsync` | 差分配布用の `.zsync` を作る |
| `win32_loader` | 旧式の win32-loader を入れる |
| `swap_file_path` / `swap_file_size` | イメージ内にスワップファイルを作る |

`[build] compression` は tar / netboot / source のアーカイブ圧縮、
`[binary] squashfs_compression` は ISO 内のライブファイルシステムの圧縮です。
スワップファイルはイメージの中に実体として入るので、ISO と USB の使用量が
その分増えます。

`hdd` や `netboot` は live-build の機能として選べますが、このツールでは
hdd のサイズ指定など一部のオプションをまだ公開していません。通常は
`iso-hybrid` を使ってください。

## Debian インストーラー

```toml
[installer]
type = "live"                 # none / cdrom / netinst / netboot / businesscard / live
gui = true
distribution = "trixie"
preseed = "./assets/preseed.cfg"

[build]
firmware_binary = true
```

| キー | 説明 |
| --- | --- |
| `type` | 同梱するインストーラーの種類。既定は `none` |
| `gui` | グラフィカルインストーラーを使うか |
| `distribution` | インストーラーのリリース。既定は `[iso] distribution` |
| `preseed` | preseed ファイル。`config/preseed/frosted.cfg` にコピーされる |
| `[build] firmware_binary` | インストーラー側にもファームウェアを入れる |

インストーラーの種類は、イメージ種別・ブートローダ・パッケージ構成と
噛み合っている必要があります。まず小さい構成で試してください。

## ファイル・スクリプト・SSH

```toml
[[files.copy]]
source = "./assets/motd"
target = "/etc/motd"
mode = "0644"
owner = "root:root"

[[files.write]]
path = "/etc/skel/.bashrc"
content = '''
export EDITOR=vim
alias ls='ls --color=auto'
'''
mode = "0644"

[scripts]
setup = ["./scripts/install-tools.sh"]      # ビルド中に chroot 内で実行
firstboot = ["./scripts/first-run.sh"]      # 初回起動時に実行

[ssh]
enable_server = true
authorized_keys = ["./keys/id_ed25519.pub"]
permit_root_login = false
password_authentication = false
```

| 機能 | 説明 |
| --- | --- |
| `files.copy` | ホストのファイル／ディレクトリをイメージ内の絶対パスへコピー |
| `files.write` | TOML に書いた内容をそのままファイルとして配置 |
| `scripts.setup` | ビルド中に chroot 内で root として実行。失敗するとビルドも失敗 |
| `scripts.firstboot` | 起動後に実行。永続化なしなら実質毎回 |
| `ssh.enable_server` | openssh-server を入れて有効化 |
| `ssh.authorized_keys` | 公開鍵を配置。鍵もパスワードも無い場合は警告 |
| `ssh.permit_root_login` | root の SSH ログインを許可 |
| `ssh.password_authentication` | パスワード認証を許可 |

`scripts.firstboot` を一度だけ実行したい場合は、`[boot] persistence = true`
と永続化パーティションを用意してください。

## ビルド環境

```toml
[build]
workdir = "build"
cache = true
compression = "xz"
apt_recommends = false
apt_proxy = "http://192.168.1.10:3142"
debootstrap_options = ""
initsystem = "systemd"
initramfs = "live-boot"
debconf_frontend = "noninteractive"
debconf_priority = "critical"
```

| キー | 説明 |
| --- | --- |
| `workdir` | live-build を走らせるディレクトリ |
| `cache` | キャッシュを残して再ビルドを速くする |
| `compression` | tar / netboot / source の圧縮 |
| `apt_recommends` | 推奨パッケージも入れる |
| `apt_proxy` | apt-cacher-ng などの HTTP プロキシ |
| `debootstrap_options` | debootstrap にそのまま渡す |
| `initsystem` | `systemd` / `sysvinit` / `none` |
| `initramfs` | `live-boot` / `none` |
| `debconf_frontend` / `debconf_priority` | debconf の挙動 |

インストール時のオプション:

```sh
sudo ./install.sh --with-deps                    # 必須のビルド依存
sudo ./install.sh --with-deps --with-additional  # QEMU/OVMF, zsync, apt-cacher-ng も
```

`--with-additional` だけでは必須依存は入りません。通常は `--with-deps` と
一緒に指定してください。

## 配布と検証

`frosted build` は ISO と一緒に次のものを作ります。

| ファイル | 内容 |
| --- | --- |
| `<ISO>.sha256` | ISO 単体の SHA256 |
| `SHA256SUMS` | 複数 ISO をまとめたチェックサム |
| `<ISO>.build-info.json` | レシピ・バージョン・ビルド環境の記録 |
| `<ISO>.asc` | `--sign` を指定したときの GPG 分離署名 |

```sh
# 署名付きでビルドする
sudo frosted build mylinux.toml --sign you@example.com

# 受け取った人はこう検証する
frosted verify mylinux-1.0-amd64.iso
frosted verify mylinux-1.0-amd64.iso --sums SHA256SUMS --signature mylinux-1.0-amd64.iso.asc
```

`--no-checksum` でチェックサムと build-info を省略できます。
`frosted verify` はチェックサムの不一致や署名の欠落を成功扱いにしません。

## プリセット

```sh
frosted presets            # 一覧
frosted presets kiosk      # 詳細
frosted init --preset kiosk --name lobby
```

| プリセット | 用途 |
| --- | --- |
| `minimal` | CUI のみ。まずビルドが通ることを確認する |
| `rescue` | ディスク復旧・診断ツール。SSH 有効 |
| `desktop` | Xfce + Firefox + LibreOffice |
| `kiosk` | 自動ログインして全画面ブラウザ。受付・掲示用 |
| `dev` | ビルドツール一式 + SSH |

プリセットは出発点です。`frosted init` の後でレシピを編集すれば、
パッケージや設定を自由に足せます。

## コマンド早見表

| コマンド | できること | よく使うオプション |
| --- | --- | --- |
| `init` | 対話でレシピを作る | `--preset` / `--name` / `--distribution` / `--arch` / `--yes` |
| `gui` | ブラウザでレシピを編集 | `--port` / `--no-browser` |
| `gen` | live-build の設定だけ生成 (root 不要) | `--quiet` |
| `build` | ISO をビルド | `--sign` / `--no-checksum` / `--output` / `--skip-preflight` |
| `validate` | レシピと環境を検証 | `--no-network` / `--no-root` |
| `show` | 内容と `lb config` 引数を表示 | `--bootappend` / `--lb-args` |
| `doctor` | ビルド環境を診断 | `--no-network` |
| `clean` | 成果物を削除 | `--all` |
| `shell` | ビルド中の chroot に入る | `--prepare` |
| `test` | QEMU で ISO を起動 | `--uefi` / `--memory` / `--no-kvm` |
| `verify` | チェックサムと署名を検証 | `--sums` / `--signature` |
| `presets` | プリセット一覧・詳細 | 名前 |

## レシピ例

### 日本語 Xfce の Live USB

```toml
version = 1

[iso]
name = "ja-live"
version = "1.0"
publisher = "Example"
preparer = "Example"

[system]
hostname = "ja-live"
locale = "ja_JP.UTF-8"
timezone = "Asia/Tokyo"
keyboard_layout = "jp"

[user]
name = "live"
fullname = "Live User"
password = "live"

[desktop]
environment = "xfce"
wallpaper = "./assets/wallpaper.png"
extra_packages = [
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
]

[boot]
persistence = true
```

### 社内パッケージと独自ミラー

```toml
version = 1

[iso]
name = "company-live"
publisher = "Example Inc."

[packages]
include = ["vim", "curl"]
local = ["./debs/company-agent_2.1.0_amd64.deb"]

[build]
repositories_in_image = true
repository_keys = ["./assets/company.gpg"]
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/company.gpg] https://repo.example.com/debian trixie main",
]

[apt]
preferences = '''
Package: *
Pin: release a=trixie
Pin-Priority: 100
'''
```

### インストーラー付き

```toml
version = 1

[iso]
name = "installer-live"
publisher = "Example"

[installer]
type = "live"
gui = true
preseed = "./assets/preseed.cfg"

[build]
firmware_binary = true
```

## まだ設定できないもの・注意

このツールは live-build の設定をかなり広く覆っていますが、すべてではありません。
現在まだレシピから指定できない主なもの:

- source イメージの種類 (`--source-images`)
- `--distribution-binary` / `--distribution-chroot`
- `--mirror-debian-installer`
- hdd のサイズ・ラベル・パーティション開始位置
- `--cache-indices` / `--cache-packages`
- live-build の `--interactive` / `--debug`
- クロスアーキテクチャ用の `--bootstrap-qemu-*`
- dm-verity、ONIE、netboot の net-root 系

その他:

- **実際の ISO ビルドは CI では通していません。** CI は生成した設定を
  本物の `lb config` に食わせるところまで確認します。最初のビルドは
  Debian マシンで `frosted doctor` を通してから実行してください。
- Windows / macOS では設定生成と検証はできますが、ISO のビルドはできません。
- `frosted test` は amd64/i386 用です。arm64 は実機か、`qemu-system-aarch64`
  と AAVMF で起動してください。
- KDE の壁紙は自動設定されません。画像はイメージ内にコピーされます。
- `sid` / `unstable` には security アーカイブがありません。
- 追加リポジトリは既定では完成イメージに残りません
  (`repositories_in_image = true` で残せます)。
- 永続化には USB 側のパーティションと `persistence.conf` が必要です。
- スワップファイルはイメージ内に実体として入るため、ISO が大きくなります。
