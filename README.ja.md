# Frosted ISO Builder

[English](README.md) | **日本語**

[![CI](https://github.com/Keychrom/Frosted-ISO-Builder/actions/workflows/ci.yml/badge.svg)](https://github.com/Keychrom/Frosted-ISO-Builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

機能の全体像と用途別の使い方は [機能一覧と使い方](FEATURES.ja.md) に
まとめています（[English](FEATURES.md)）。

Debian の Live ISO を、**レシピ 1 枚**から作るツールです。

live-build のラッパーです。live-build をそのまま使うと、`config/` ツリー・
`auto/config`・3 段階のフックという別々の仕組みを理解して設定しないといけません。
このツールはその部分を全部引き受けて、利用者には「何を作りたいか」だけを
書いてもらいます。

```toml
[iso]
name = "mylinux"

[desktop]
environment = "xfce"
```

これだけでビルドできます。配布するための成果物 (チェックサム・ビルド情報・
GPG 署名) も作れるので、公開する ISO のリリース作業までこれ 1 つで回せます。

---

## 目次

- [必要な環境](#必要な環境)
- [インストール](#インストール)
- [5 分で試す](#5-分で試す)
- [機能一覧と使い方](FEATURES.ja.md)
- [レシピのリファレンス](#レシピのリファレンス)
- [コマンド一覧](#コマンド一覧)
- [プリセット](#プリセット)
- [デスクトップ環境](#デスクトップ環境)
- [ISO を配布する](#iso-を配布する)
- [仕組み](#仕組み)
- [永続化 (persistence)](#永続化-persistence)
- [トラブルシューティング](#トラブルシューティング)
- [開発に参加する](#開発に参加する)
- [検証状況](#検証状況)
- [ライセンス](#ライセンス)

---

UI は日本語と英語に対応しています。環境変数 `LANG` / `LC_ALL` から自動で判定し、
`--lang ja` / `--lang en` で明示的に指定することもできます。

## 必要な環境

| | |
| --- | --- |
| OS | Debian 12 (bookworm) または 13 (trixie)。その派生でも可 |
| Python | 3.11 以上 (標準ライブラリしか使いません) |
| 権限 | ビルド時に root |
| 空き容量 | 最低 6 GiB、快適に作るなら 20 GiB 以上 |
| ネットワーク | APT ミラーに到達できること |

ビルドは root 権限で動かす必要があり、live-build は chroot を作るので
コンテナの中ではうまく動かないことがあります。実機か VM で動かしてください。

## インストール

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder

# 依存パッケージごと入れる場合 (推奨)
sudo ./install.sh --with-deps

# 任意ツール (QEMU/OVMF, zsync, apt-cacher-ng) も一緒に入れる場合
sudo ./install.sh --with-deps --with-additional

# 任意ツールだけあとから足す場合
sudo ./install.sh --with-additional

# 依存は自分で入れる場合
sudo ./install.sh
```

`--with-additional` で入るのは、無くてもビルドできるが便利なものです。
QEMU と OVMF は `frosted test` / `frosted test --uefi` の起動確認、
`zsync` は `[binary] zsync` の差分ファイル、`apt-cacher-ng` は再ビルド時の
パッケージ取得の高速化に使います。`--with-additional` だけでは必須の
ビルド依存は入らないので、通常は `--with-deps` と一緒に指定してください。

`--with-deps` を使わない場合は、先にこちらを実行してください。

```sh
sudo apt install live-build debootstrap xorriso squashfs-tools cpio rsync \
    uuid-runtime mtools dosfstools syslinux-common isolinux \
    grub-efi-amd64-bin grub-pc-bin fakeroot gnupg
```

arm64 では amd64/x86 用の GRUB パッケージの代わりに `grub-efi-arm64-bin` を
入れてください。`./install.sh --with-deps` はホストに合うものを選びます。

インストールせずに試すこともできます。

```sh
python3 bin/frosted --version
```

アンインストールは `sudo ./install.sh --uninstall` です。apt で入れた
パッケージは残るので、不要なら手で消してください。

## 5 分で試す

```sh
# 1. 環境を診断する。足りないものが分かる
frosted doctor

# 2. 対話でレシピを作る
frosted init

# 3. 設定がどうなるか先に見る (root 不要・数秒で終わる)
frosted gen mylinux.toml

# 4. ビルドする。数十分かかる
sudo frosted build mylinux.toml

# 5. USB に焼く前に QEMU で起動を確認する
frosted test mylinux.toml
```

`init` はホストのタイムゾーン・キーボード・ロケールを既定値として拾うので、
たいていは Enter だけで進めます。

まずは [`examples/minimal.toml`](examples/minimal.toml) でビルドが通ることを
確かめるのがおすすめです。CUI だけの素の Debian が 10 分ほどでできます。

```sh
sudo frosted build examples/minimal.toml
```

## レシピのリファレンス

レシピは TOML です。書かなかった項目には既定値が入るので、
必要なところだけ書けば済みます。

### `[iso]` — 作るもの

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `name` | (必須) | ISO の名前。英小文字・数字・ハイフンのみ |
| `version` | `"1.0"` | バージョン。出力ファイル名に入る |
| `label` | 名前から生成 | ISO のボリュームラベル。32 文字以内 |
| `distribution` | `trixie` | `trixie` (13) / `bookworm` (12) / `testing` / `sid` (`forky`・`unstable` も可) |
| `architecture` | `amd64` | `amd64` / `i386` / `arm64` |
| `output` | 自動生成 | 出力ファイル名。既定は `<名前>-<版>-<arch>.iso` |
| `publisher` | ツール名 | ISO に書き込む発行元。**配布するなら必ず設定する** |
| `preparer` | ツール名 | ISO に書き込む作成者。**配布するなら必ず設定する** |
| `application` | `name` と同じ | ISO のアプリケーション識別子 |

`publisher` と `preparer` は ISO の中に記録され、受け取った人が
`isoinfo -d -i image.iso` などで確認できます。既定ではこのツール名が
入ってしまうので、公開するイメージでは自分の名前かプロジェクト名に
書き換えてください。

`testing` は Debian Testing (現在は `forky`)、`sid` は unstable です。
どちらも開発版で、パッケージが動き続けるため、昨日ビルドできた構成が
今日壊れることがあります。`sid` には security アーカイブが無いので、
`build.security_mirror` は無視されます。

### `[system]` — 地域と言語

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `hostname` | `debian` (ウィザードでは ISO 名) | ホスト名 |
| `locale` | `en_US.UTF-8` | ロケール。`ja_JP.UTF-8` など |
| `timezone` | `UTC` | `Asia/Tokyo` など |
| `keyboard_layout` | `us` | `jp` など |
| `keyboard_variant` | 空 | かな入力などを使うとき |
| `keyboard_model` | `pc105` | 通常は変更不要 |
| `utc` | `true` | ハードウェア時計を UTC で扱うか |

### `[user]` — ライブ環境のユーザー

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `name` | `user` | ユーザー名 |
| `fullname` | `Live User` | 表示名 |
| `password` | 空 | 空ならパスワード無し。`$6$...` を書くとハッシュ扱い |
| `root_password` | 空 | root のパスワード |
| `default_groups` | 空 | 追加で所属させるグループ (`sudo,dialout` など) |
| `autologin` | `true` | 起動時に自動ログインするか |
| `sudo` | `true` | パスワード無しの sudo を許可するか |

### `[desktop]` — デスクトップ環境

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `environment` | `none` | [`none` / `xfce` / `lxqt` / `mate` / `gnome` / `kde` / `cinnamon`](#デスクトップ環境) |
| `session_manager` | 自動 | X セッションの指定。通常は変更不要 |
| `extra_packages` | 空 | デスクトップ環境に追加で入れるパッケージ |
| `wallpaper` | 空 | イメージにコピーし、ログイン時に設定する壁紙画像 |

```toml
[desktop]
environment = "xfce"
wallpaper = "./assets/wallpaper.jpg"
```

壁紙は Xfce / GNOME / MATE / Cinnamon / LXQt でログイン時に設定されます。
KDE ではイメージ内にコピーされるだけで、自動設定は行いません。
対応形式は PNG / JPEG / WebP / SVG です。

### `[packages]` — パッケージ

| キー | 説明 |
| --- | --- |
| `include` | 追加で入れるパッケージの配列 |
| `exclude` | 明示的に削除するパッケージの配列 |
| `local` | 同梱するホスト上の `.deb` の配列 |

`exclude` はインストール後に `apt-get remove` します。依存関係をたどった
自動削除はしないので、名指ししたものだけが消えます。

`local` は自前でビルドしたパッケージを入れるときに使います。
live-build が `config/packages.chroot/` からローカルリポジトリを作り、
依存関係ごとインストールします。

```toml
[packages]
local = [
  "./debs/myapp_1.2.0_amd64.deb",
  "./debs/myapp-data_1.2.0_all.deb",
]
```

ファイル名は dpkg が付けた `_all.deb` または `_<アーキテクチャ>.deb` の
ままにしてください。live-build はそれ以外の名前を拾わないため、検証で
エラーにしています。

### `[ssh]`

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `enable_server` | `false` | openssh-server を入れ、起動時に有効にする |
| `authorized_keys` | 空 | 公開鍵ファイルのパス (ホスト側) |
| `permit_root_login` | `false` | root での SSH ログインを許すか |
| `password_authentication` | `false` | パスワード認証を許すか |

鍵もパスワードも設定しないとログインできないので、その組み合わせは
検証時に警告が出ます。

### `[[files.copy]]` / `[[files.write]]` — ファイルを入れる

```toml
# ホストのファイルをイメージに入れる
[[files.copy]]
source = "./assets/motd"     # レシピからの相対パス
target = "/etc/motd"         # イメージ内の絶対パス
mode = "0644"                # 省略可
owner = "root:root"             # 省略可 (旧名: Keychrom)

# 中身を直接書いてイメージに入れる
[[files.write]]
path = "/etc/skel/.bashrc"
content = '''
export EDITOR=vim
alias ls='ls --color=auto'
'''
mode = "0644"
```

`content` は `'''` で囲んだ複数行文字列が使えます。シェルスクリプトを
そのまま貼れて、エスケープを考えなくて済みます。

`files.copy` の `source` にディレクトリを指定すると、中身ごとコピーされます。

### `[scripts]` — スクリプトを走らせる

```toml
[scripts]
setup = ["./scripts/install-tools.sh"]     # ビルド時に chroot 内で実行
firstboot = ["./scripts/first-run.sh"]     # 初回起動時に実行
```

`setup` はビルド中に chroot の中で root として走ります。パッケージを入れたり
設定を書き換えたりするのに使います。途中で失敗するとビルドも失敗します。

`firstboot` は起動後に走ります。**永続化を有効にしていない場合、ライブ環境は
起動のたびにまっさらな状態に戻るので、実質「毎回」実行されます。**
一度だけにしたいときは [`boot.persistence`](#永続化-persistence) を有効にしてください。

### `[boot]`

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `append` | 空 | 追加のカーネルパラメータ。`quiet splash toram` など |
| `install_append` | 空 | インストーラーで導入したシステムに入れるカーネルパラメータ |
| `persistence` | `false` | 永続化を有効にする |
| `failsafe_noautologin` | `true` | failsafe メニューで自動ログインを切るか |

### `[build]` — ビルドの設定

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `workdir` | `"build"` | live-build を走らせるディレクトリ |
| `mirror` | `http://deb.debian.org/debian/` | APT ミラー。社内ミラーがあればここ |
| `security_mirror` | `http://security.debian.org/...` | セキュリティ更新のミラー (`sid`/`unstable` では無視) |
| `archive_areas` | `main contrib non-free-firmware` | 有効にするアーカイブ領域 |
| `compression` | `xz` | tar/netboot/source のアーカイブ圧縮 (`xz` / `gzip` / `bzip2` / `lzip` / `none`) |
| `apt_recommends` | `false` | 推奨パッケージも入れるか |
| `apt_proxy` | 空 | `http://192.168.1.10:3142` など。再ビルドが速くなる |
| `cache` | `true` | キャッシュを残して再ビルドを速くするか |
| `firmware` | `true` | ファームウェアを入れるか (Wi-Fi・GPU に必要) |
| `bootloaders` | `syslinux grub-efi` | BIOS と UEFI の両対応 |
| `secure_boot` | `auto` | `auto` / `enable` / `disable` |
| `memtest` | `false` | メモリテストのエントリを入れるか |
| `debootstrap_options` | 空 | そのまま debootstrap に渡す |
| `extra_repositories` | 空 | 追加の APT リポジトリ (`deb ...` の行) |
| `repository_keys` | 空 | 追加リポジトリ用の GPG 鍵。apt に登録し、`/usr/share/keyrings/` にもコピーする |
| `repositories_in_image` | `false` | 追加リポジトリを完成イメージの sources.list にも残す |
| `firmware_binary` | `false` | インストーラー側にもファームウェアを入れる |
| `initsystem` | `systemd` | `systemd` / `sysvinit` / `none` |
| `initramfs` | `live-boot` | `live-boot` / `none` |
| `updates` | 未指定 | updates スイートを有効にする |
| `backports` | 未指定 | backports を有効にする |
| `proposed_updates` | 未指定 | proposed-updates を有効にする |
| `security` | 未指定 | security スイートを有効にする (`sid`/`unstable` では無視) |
| `source` | 未指定 | source イメージも作る |
| `debconf_frontend` | 未指定 | `dialog` / `editor` / `noninteractive` / `readline` |
| `debconf_priority` | 未指定 | `low` / `medium` / `high` / `critical` |

鍵のファイル名は半角英数字・`.`・`_`・`-` のみで、拡張子は
`.gpg` / `.asc` / `.pgp` のいずれかにしてください。パッケージ導入時に
apt が使えるよう `config/archives/` に置かれ、同じファイル名でイメージ内の
`/usr/share/keyrings/` にもコピーされます (`signed-by=` 用)。

追加リポジトリは既定では**パッケージ導入時だけ**使われ、完成イメージの
`sources.list` には残りません。ライブ環境でも `apt` でそのミラーを使いたい
ときは `repositories_in_image = true` にしてください。鍵は `repository_keys`
に入れておけば `/usr/share/keyrings/` に残ります。

```toml
[build]
repositories_in_image = true
extra_repositories = [
  "deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://repo.example.com/debian stable main",
]
repository_keys = ["./assets/myrepo.gpg"]
```

### `[apt]` — APT の挙動

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `backend` | 未指定 | `apt` / `apt-get` / `aptitude` |
| `secure` | 未指定 | リポジトリの署名を検証するか |
| `source_archives` | 未指定 | `deb-src` を含めるか |
| `indices` | 未指定 | パッケージインデックスをイメージに残すか |
| `options` | 空 | APT に渡す 1 つの文字列。例: `--no-install-recommends` |
| `pipeline` | 未指定 | APT のパイプライン段数 |
| `keyring_packages` | 空 | APT 用に導入する鍵パッケージ |
| `preferences` | 空 | APT のピン留め。`config/archives/frosted.pref` にそのまま書く |

推奨パッケージと HTTP プロキシは従来どおり `[build] apt_recommends` と
`[build] apt_proxy` で指定します。

複数のリポジトリを混ぜるときは、優先度を明示すると意図しない版が
入るのを防げます。

```toml
[apt]
preferences = '''
Package: *
Pin: release a=trixie
Pin-Priority: 100
'''
```

### `[installer]` — Debian インストーラー

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `type` | `none` | `none` / `cdrom` / `netinst` / `netboot` / `businesscard` / `live` |
| `gui` | 未指定 | グラフィカルインストーラーを使うか |
| `distribution` | `iso.distribution` と同じ | インストーラーのリリース |
| `preseed` | 空 | ホスト上の preseed。`config/preseed/frosted.cfg` にコピー |

インストーラーの種別は `[binary] image_type`、ブートローダ、イメージ構成と
噛み合っている必要があります。まず小さい構成で試してください。

### `[kernel]` — カーネルパッケージ

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `packages` | 空 | 例: `linux-image` |
| `flavours` | 空 | 例: `["amd64"]` / `["686-pae"]` |

### `[binary]` — イメージ構成と圧縮

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `image_type` | `iso-hybrid` | `iso` / `iso-hybrid` / `netboot` / `tar` / `hdd` |
| `filesystem` | 未指定 | `fat16` / `fat32` / `ext2` / `ext3` / `ext4` / `ntfs` |
| `checksums` | `sha256` | `md5` / `sha1` / `sha224` / `sha256` / `sha384` / `sha512` / `none` |
| `chroot_filesystem` | 未指定 | `ext2` / `ext3` / `ext4` / `squashfs` / `jffs2` / `none` |
| `squashfs_compression` | `xz` | `gzip` / `lzma` / `lzo` / `lz4` / `xz` / `zstd` |
| `squashfs_compression_level` | 未指定 | mksquashfs の圧縮レベル |
| `initramfs_compression` | 未指定 | `bzip2` / `gzip` / `lzma` |
| `zsync` | 未指定 | 差分ダウンロード用の zsync を作る |
| `win32_loader` | 未指定 | 旧式の win32-loader を入れる |
| `swap_file_path` | 未指定 | イメージ内に作るスワップファイル。例: `/swapfile` |
| `swap_file_size` | `512` | スワップファイルの大きさ (MB) |

```toml
[binary]
image_type = "iso-hybrid"
squashfs_compression = "zstd"
squashfs_compression_level = 19
checksums = "sha256"
swap_file_path = "/swapfile"
swap_file_size = 1024
```

`[build] compression` は tar/netboot/source のアーカイブ圧縮、
`[binary] squashfs_compression` は ISO 内のライブファイルシステムの圧縮です。
スワップファイルはイメージの中に実体として入るので、その分 ISO と
書き込んだ USB の使用量が増えます。RAM の少ない実機向けです。

## コマンド一覧

| コマンド | 説明 |
| --- | --- |
| `init` | 対話でレシピを作る |
| `gen` | live-build の設定だけ生成する (**root 不要**) |
| `build` | ISO をビルドする |
| `validate` | レシピと環境を検証する |
| `show` | レシピの内容とブートパラメータを表示する |
| `doctor` | ビルド環境を診断する |
| `presets` | プリセットの一覧・詳細 |
| `clean` | 作業ディレクトリの成果物を消す |
| `shell` | ビルド途中の chroot に入る |
| `test` | QEMU で ISO を起動する |
| `verify` | 配布された ISO のチェックサムと署名を検証する |

よく使う組み合わせ:

```sh
# 対話を飛ばしてプリセットから作る
frosted init --preset kiosk --name lobby --output lobby.toml

# 設定だけ生成して中身を目で確認する
frosted gen mylinux.toml
less mylinux.toml.build/auto/config

# ブートパラメータだけ見る
frosted show mylinux.toml --bootappend

# lb config に渡す引数をそのまま見る
frosted show mylinux.toml --lb-args

# キャッシュも含めて全部消す
frosted clean mylinux.toml --all
```

## プリセット

| 名前 | 内容 |
| --- | --- |
| `minimal` | CUI のみの素の Debian。最初のビルド確認に |
| `rescue` | ディスク復旧・診断ツール一式 + SSH |
| `desktop` | Xfce + Firefox + LibreOffice |
| `kiosk` | 自動ログインして全画面ブラウザが開く |
| `dev` | ビルドツール一式 + SSH |

```sh
frosted presets kiosk     # 中身を確認
frosted init --preset kiosk
```

## デスクトップ環境

| キー | 環境 | 目安サイズ | ディスプレイマネージャ |
| --- | --- | --- | --- |
| `none` | なし (CUI) | 約 350 MB | — |
| `xfce` | Xfce | 約 1.2 GB | lightdm |
| `lxqt` | LXQt | 約 1.1 GB | sddm |
| `mate` | MATE | 約 2.0 GB | lightdm |
| `gnome` | GNOME | 約 3.0 GB | gdm3 |
| `kde` | KDE Plasma | 約 3.2 GB | sddm |
| `cinnamon` | Cinnamon | 約 2.2 GB | lightdm |

自動ログインの設定はディスプレイマネージャごとに書き分けています。
`user.autologin` を `true` にしていれば、どの環境でも起動時に勝手に
ログインします。

## ISO を配布する

配布するときはイメージ本体だけでは足りません。受け取った人が「これは本当に
その配布元が作ったものか」「中身は何か」を確かめられる必要があります。
`build` は次のものを ISO の隣に作ります。

| ファイル | 中身 |
| --- | --- |
| `SHA256SUMS` | まとめて検証できる慣習的な形式 |
| `<ISO名>.sha256` | 単体で配る用 |
| `<ISO名>.build-info.json` | 何をどうやって作ったかの記録 |
| `<ISO名>.asc` | GPG の分離署名 (`--sign` を付けたときだけ) |

```sh
# 署名付きでビルドする
sudo frosted build release.toml --sign you@example.com
```

`build-info.json` にはレシピのハッシュ、入れたパッケージの一覧とバージョン、
実際に渡したオプション、ISO のハッシュと大きさが入ります。あとから
「この ISO はどのレシピのどの版から作られたか」を辿れます。

配布するときは ISO と一緒にこれらのファイルも渡してください。受け取った側は
こうやって検証できます。

```sh
frosted verify mylinux-1.0-amd64.iso
```

`verify` はチェックサムと署名を確認し、ビルド情報を表示します。結果は
分かりやすく表示します。`sha256sum -c SHA256SUMS` や
`gpg --verify` を直接使っても構いません。

### 公開前のチェックリスト

- [ ] `[iso] publisher` と `preparer` を自分の名前かプロジェクト名にした
- [ ] `[iso] version` を上げた
- [ ] `user.password` に仮のパスワードが残っていないか確認した
- [ ] `user.autologin` と `user.sudo` の設定が意図どおり
- [ ] `ssh.authorized_keys` に他人の鍵が入っていないか確認した
- [ ] `frosted test` で BIOS と UEFI の両方で起動を確認した
- [ ] `--sign` で署名した

## 仕組み

```
レシピ (TOML)
    │
    │  frosted gen
    ▼
<作業ディレクトリ>/
├── auto/config                     ← lb config に渡す全オプション
├── config/package-lists/*.list.chroot
├── config/includes.chroot/         ← イメージに入れるファイル
├── config/hooks/live/*.hook.chroot ← ビルド時に chroot 内で走る
└── .frosted-manifest.json          ← 生成物の一覧 (再生成時の掃除に使う)
    │
    │  frosted build
    ▼
   ISO + SHA256SUMS + build-info.json (+ .asc)
```

このツリーは live-build がそのまま理解できる形式なので、このツールを
経由せず `cd <作業ディレクトリ> && sudo lb build` でビルドすることもできます。

### このツールが引き受けている面倒

- **`lb config` のオプション組み立て** — 60 個近いオプションをレシピから導出
- **ブートパラメータ** — `hostname=` `username=` `locales=` `keyboard-layouts=`
  などを正しい綴りで組み立て (このへんは間違えやすい)
- **自動ログインの設定** — lightdm / sddm / gdm3 それぞれの書き方
- **ユーザー周りの起動時処理** — live 環境のユーザーは起動時に作られるので、
  パスワードや SSH 鍵はビルド時には書けない。systemd ユニットを仕込んで
  起動後に一度だけ処理する
- **後片付け** — apt キャッシュ・ログ・machine-id を消してイメージを小さく保つ

### live-build のバージョン差への対応

`lb config` のオプション名は live-build のバージョンによって単数形/複数形が
揺れています (`--architecture` と `--architectures` など)。このツールは
生成前に `lb config --help` を読んで、**実際に使えるほうの綴りを選びます。**
`frosted doctor` でその確認結果が見られます。

この解決が正しく効いているかは、CI で実際の live-build と突き合わせて
検証しています (`tests/test_lb_integration.py`)。

## 永続化 (persistence)

ライブ環境の変更を USB に保存したい場合、レシピで有効にできます。

```toml
[boot]
persistence = true
```

ただし**これだけでは足りません。** USB 側に別途準備が必要です。

1. USB に `persistence` というラベルのパーティションを作る
2. その直下に `persistence.conf` を置く

```sh
# USB が /dev/sdb で、2 番目のパーティションを persistence にする例
sudo mkfs.ext4 -L persistence /dev/sdb2
sudo mkdir -p /mnt/persist
sudo mount /dev/sdb2 /mnt/persist
echo "/ union" | sudo tee /mnt/persist/persistence.conf
sudo umount /mnt/persist
```

`/ union` はルート全体を保存するという意味です。`/home union` のように
特定のディレクトリだけにすることもできます。

## トラブルシューティング

### `frosted doctor` を最初に走らせる

足りないものと対処法が出ます。まずこれ。

### ビルドが途中で落ちる

ビルドのログは作業ディレクトリの `build.log` に全部残ります。
`lb build` の出力がそのまま入っているので、たいていは原因が分かります。

```sh
less <作業ディレクトリ>/build.log
```

### オプションが不正と言われる

live-build のバージョンによる綴りの違いです。

```sh
frosted doctor <レシピ>
```

`lb オプション` の行に、対応していない設定が警告として出ます。

### 2 回目のビルドがおかしい

live-build は前回の設定を引きずることがあります。設定だけ作り直すには:

```sh
frosted gen <レシピ>      # 設定を再生成
sudo frosted build <レシピ>
```

それでも直らないときは、キャッシュごと消してやり直します。

```sh
frosted clean <レシピ> --all
```

### 起動はするが自動ログインしない

ディスプレイマネージャが想定どおりか確認してください。ビルド時に
`frosted gen` の出力の `0200-autologin.hook.chroot` を見ると、
どのファイルを書こうとしているか分かります。

起動後なら、ログイン画面で Ctrl-Alt-F2 を押してコンソールに出て、
ユーザーと root のパスワードで入って調べられます。

```sh
systemctl status frosted-boot-setup
journalctl -u frosted-boot-setup
```

### USB に焼く

```sh
sudo dd if=mylinux-1.0-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

**`/dev/sdX` は必ず自分の環境に合わせて確認してください。間違えるとその
ディスクの中身が全部消えます。** `lsblk` で確認してから実行してください。

複数の ISO を 1 本の USB に入れたいなら [Ventoy](https://www.ventoy.net/) が便利です。

## 開発に参加する

実行時の依存はありません。Python 3.11 以上があれば開発できます。

```sh
git clone https://github.com/Keychrom/Frosted-ISO-Builder
cd Frosted-ISO-Builder

# テスト (標準ライブラリの unittest のみ)
python3 -m unittest discover -s tests -t . -v

# インストールせずに実行する
python3 bin/frosted --help
```

### 構成

| 場所 | 役割 |
| --- | --- |
| `frosted/recipe.py` | レシピのデータモデルと検証。ここが唯一の真実 |
| `frosted/catalog.py` | デスクトップ環境とプリセットの一覧。追加はここだけ |
| `frosted/backend/livebuild.py` | レシピ → live-build ツリーの変換。このツールの核 |
| `frosted/preflight.py` | ビルド前の環境診断 |
| `frosted/release.py` | チェックサム・ビルド情報・署名 |
| `frosted/wizard.py` | 対話ウィザード |
| `frosted/cli.py` | コマンドライン |

### UI の文言を足すとき

日本語の原文がそのまま翻訳のキーになっています (`frosted/i18n_en.py`)。
`tests/test_i18n.py` は CLI を英語モードで走らせて、出力に日本語が残って
いたら失敗します。文言を足したらこのテストを走らせてください。

### 気をつけること

- **生成物は必ず LF 改行で書く。** CRLF になると Linux 側で
  `/bin/sh^M` として実行できなくなります (`_write_file` の `newline="\n"`)。
- **`auto/config` の `noauto` を外さない。** 無いと live-build が再帰します。
- **`auto/build` と `auto/clean` は作らない。** live-build が自動で呼ぶため、
  中で `lb build` を呼ぶと再帰する危険があります。
- **レシピに項目を足したら、生成物に反映されることをテストする。**
  `RecipeKnobsReachTheOutputTest` がそのための場所です。
- **`lb config` のオプション名を決め打ちしない。** `OPTION_ALIASES` に候補を
  書けば、実行時に使える綴りが選ばれます。

## 検証状況

正直に書いておきます。

**検証済み (自動テスト一式 + CI)**

- レシピの読み書き・検証 (誤った入力の検出、TOML の往復)
- live-build ツリーの生成内容
- 生成したシェルスクリプトの構文 (`sh -n` による解析)
- 偽の `lb` を差し込んだ `auto/config` の実行と、引数の引用符の正しさ
- 生成物が LF 改行であること
- チェックサム・ビルド情報の生成と、破損・改ざんの検出
- 全プリセット・全デスクトップ環境でのツリー生成
- **実際の live-build が生成した設定を受け付けること** (CI の
  `live-build` ジョブで `lb config` に食わせて確認)
- 英語モードの出力に日本語が残っていないこと

**未検証**

- **実際の ISO ビルドはまだ通していません。** Debian マシン上での
  `sudo frosted build` がまだ実行されていません。
- ビルドした ISO の起動確認
- 自動ログイン・SSH 鍵配備・パスワード設定の実機での動作
  (起動時の systemd ユニットは仕込まれるところまでしか確認できていません)

最初のビルドは [`examples/minimal.toml`](examples/minimal.toml) で
通してください。ここが通れば、あとはパッケージとデスクトップを足すだけです。

何かおかしければ、`build.log` と `frosted doctor` の出力を見れば
だいたい分かります。

## ライセンス

[MIT](LICENSE)
