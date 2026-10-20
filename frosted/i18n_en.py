"""英語の翻訳カタログ。

キーは日本語の原文、値が英語。仕組みは `frosted/i18n.py` の説明を参照。

`EN` に無いものは `PREFIXES` (「前置き: 値」形式) → `PATTERNS` (正規表現)
の順に探す。どれにも当てはまらなければ日本語のまま表示される。
漏れは `tests/test_i18n.py` が検出するので、文言を足したらテストを走らせること。
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------
# そのまま置き換える文
# --------------------------------------------------------------------------

EN: dict[str, str] = {
    # ---- ui.py ----------------------------------------------------------
    "1 から {count} の番号で答えてください。": "Enter a number from 1 to {count}.",
    "入力してください。": "Please enter a value.",
    "括弧内が既定値です。そのまま使うなら {key} を押してください。": (
        "The value in brackets is the default; press {key} to accept it."
    ),
    "いつでも {key} で中断できます。": "You can press {key} at any time to abort.",
    "プリセット「{name}」を適用しました。": "Applied the {name} preset.",
    "イメージの大きさの目安: 約 {size} MB": "Roughly {size} MB of image",
    "y か n で答えてください。": "Please answer y or n.",
    "一致しません。もう一度入力してください。": "They do not match. Please try again.",
    "入力が終了しました。": "Input ended.",
    "確認のためもう一度: ": "Again to confirm: ",
    " (入力は画面に出ません): ": " (input is hidden): ",
    # ---- errors.py ------------------------------------------------------
    "操作を中断しました。": "Aborted.",
    # ---- runner.py ------------------------------------------------------
    "root 権限が必要ですが sudo が見つかりません。": (
        "Root privileges are required but sudo was not found."
    ),
    "root でログインし直すか、sudo をインストールしてください。": (
        "Log in as root, or install sudo."
    ),
    "live-build 一式がインストールされているか確認してください。 `frosted doctor` で診断できます。": (
        "Check that live-build and its dependencies are installed. "
        "Run `frosted doctor` to diagnose."
    ),
    # ---- release.py -----------------------------------------------------
    "gpg が見つかりません。": "gpg was not found.",
    "sudo apt install gnupg で入れてください。": (
        "Install it with: sudo apt install gnupg"
    ),
    # ---- preflight.py ---------------------------------------------------
    "/etc/os-release が読めません (Linux 以外で実行している可能性があります)": (
        "/etc/os-release is not readable (you may not be running on Linux)"
    ),
    "不明": "unknown",
    "root で実行中": "running as root",
    "root ではありません": "not running as root",
    "ビルドは Debian 上で root として実行する必要があります。": (
        "Building must be run as root on Debian."
    ),
    "sudo を付けて実行してください: sudo frosted build <レシピ>": (
        "Run it with sudo: sudo frosted build <recipe>"
    ),
    "QEMU (frosted test で起動確認するときに使う)": (
        "QEMU (used by `frosted test` to try booting the image)"
    ),
    "apt-cacher-ng (再ビルド時のパッケージ取得を速くする)": (
        "apt-cacher-ng (speeds up package downloads on rebuilds)"
    ),
    "zsync (差分配布用の .zsync を作るときに使う)": (
        "zsync (creates .zsync files for delta distribution)"
    ),
    "debootstrap (Debian の最小システムを展開する)": (
        "debootstrap (unpacks a minimal Debian system)"
    ),
    "xorriso (ISO イメージを書き出す)": "xorriso (writes the ISO image)",
    "squashfs-tools (ライブファイルシステムを作る)": (
        "squashfs-tools (creates the live filesystem)"
    ),
    "cpio (initramfs の展開に必要)": "cpio (needed to unpack the initramfs)",
    "uuid-runtime (UUID の生成に必要)": "uuid-runtime (needed to generate UUIDs)",
    "すべて見つかりました": "all found",
    "無くてもビルドできますが、あると便利です。": (
        "Building works without them, but they are handy."
    ),
    "ホストの種類を判定できません": "cannot determine the host architecture",
    "live-build は Debian 系を前提にしています。他のディストロでは動かない可能性があります。": (
        "live-build assumes a Debian-based system. "
        "It may not work on other distributions."
    ),
    "クロスビルドには qemu-user-static と binfmt の設定が必要で、とても遅くなります。同じアーキテクチャのマシンでビルドするのを勧めます。": (
        "Cross-building needs qemu-user-static and binfmt configuration, "
        "and is very slow. Build on a machine of the same architecture instead."
    ),
    "`lb config --help` を読めませんでした": "could not read `lb config --help`",
    "既定の綴りで生成します。ビルドが通れば問題ありません。": (
        "Falling back to the documented option names. "
        "If the build succeeds, you are fine."
    ),
    "lb が見つからないため確認できません": "cannot check because lb was not found",
    "一部の設定が反映されません": "some settings will not take effect",
    "URL ではないので確認を省略しました: ": "skipped, not an HTTP URL: ",
    "ネットワークが無い、またはプロキシが必要かもしれません。 社内ミラーを使うなら build.mirror を書き換えてください。": (
        "There may be no network access, or a proxy may be required. "
        "If you use an internal mirror, change build.mirror."
    ),
    "ミラーの URL か、そのディストリビューション名を確認してください。": (
        "Check the mirror URL, and that the distribution exists on it."
    ),
    "上の [x] の項目を解消してから、もう一度実行してください。": (
        "Fix the items marked [x] above and run it again."
    ),
    "必要なものをまとめて入れるには:": "To install everything needed at once:",
    "この環境ではビルドできません。": "This machine cannot build images.",
    "ビルドできる環境です。": "This environment is ready to build.",
    "警告が {count} 件ありますが、ビルドはできます。": (
        "{count} warning(s), but the build can proceed."
    ),
    "この環境でビルドできます。": "This machine can build images.",
    "レシピが指定されていないので、既定の設定で環境だけ確認します。": (
        "No recipe given, so only the environment was checked using default settings."
    ),
    "ビルドできない問題が {count} 件あります。": (
        "{count} problem(s) will prevent building."
    ),
    "レシピに問題があります": "the recipe has problems",
    # ---- catalog.py: デスクトップ環境 ------------------------------------
    "なし (CUI)": "None (console only)",
    "X もデスクトップも入れない最小構成。レスキューやサーバー用途。": (
        "No X, no desktop environment. For rescue or server use."
    ),
    "軽くて安定。Live USB の定番。初めてならこれ。": (
        "Light and stable. The usual choice for a live USB. Start here."
    ),
    "Xfce よりさらに軽い。古いマシンやキオスク向け。": (
        "Even lighter than Xfce. Good for old machines and kiosks."
    ),
    "GNOME 2 の流れをくむ伝統的なデスクトップ。": (
        "A traditional desktop in the GNOME 2 lineage."
    ),
    "標準的で高機能。そのぶん重い (2GB 以上推奨)。": (
        "Full-featured and standard, but heavy (2 GB or more recommended)."
    ),
    "高機能で見た目も良い。重め。": "Feature-rich and good-looking. On the heavy side.",
    "Windows に近い操作感。": "Feels close to Windows.",
    "イメージの大きさの目安: 約 {size} MB": "Roughly {size} MB of image",
    # ---- catalog.py: 言語サポート ----------------------------------------
    "追加なし": "None",
    "英語のみ。イメージが小さくなる。": "English only. Keeps the image small.",
    "日本語": "Japanese",
    "日本語フォント、かな漢字変換 (fcitx5 + mozc)、日本語ドキュメント。": (
        "Japanese fonts, kana-kanji input (fcitx5 + mozc), Japanese documentation."
    ),
    "韓国語": "Korean",
    "韓国語フォントと入力メソッド。": "Korean fonts and input method.",
    "中国語": "Chinese",
    "中国語フォントと入力メソッド。": "Chinese fonts and input method.",
    # ---- catalog.py: プリセット ------------------------------------------
    "最小構成": "Minimal",
    "CUI のみの素の Debian Live。まずはこれでビルドが通ることを確かめるのに向く。": (
        "A plain console-only Debian live image. "
        "Good for checking that building works at all."
    ),
    "レスキュー": "Rescue",
    "ディスク復旧・診断ツール一式。SSH 有効。壊れたマシンの救出用。": (
        "A full set of disk recovery and diagnostic tools, with SSH enabled. "
        "For rescuing broken machines."
    ),
    "デスクトップ": "Desktop",
    "Xfce + Firefox + LibreOffice。普段使いの Live USB。": (
        "Xfce with Firefox and LibreOffice. An everyday live USB."
    ),
    "キオスク端末": "Kiosk",
    "起動すると自動ログインして全画面ブラウザが開く。受付端末や掲示用。": (
        "Boots, logs in automatically and opens a full-screen browser. "
        "For reception desks and signage."
    ),
    "開発環境": "Development",
    "ビルドツール一式 + SSH。持ち運べる開発環境。": (
        "A full set of build tools plus SSH. A portable development environment."
    ),
    # ---- cli.py: 説明 ---------------------------------------------------
    "Frosted ISO Builder — Debian Live ISO をレシピ 1 枚から作るツール。": (
        "Frosted ISO Builder — build Debian live ISOs from a single recipe file."
    ),
    "対話でレシピファイルを作る": "Create a recipe file interactively",
    "live-build の設定だけ生成する (ビルドはしない)": (
        "Generate the live-build configuration only (do not build)"
    ),
    "レシピから ISO をビルドする": "Build the ISO from a recipe",
    "レシピと環境を検証する (ビルドはしない)": (
        "Validate the recipe and the environment (do not build)"
    ),
    "レシピの内容を表示する": "Show the contents of a recipe",
    "ビルド環境を診断する": "Diagnose the build environment",
    "作業ディレクトリを掃除する": "Clean the work directory",
    "ビルド途中の chroot に入る": "Open a shell in the build chroot",
    "QEMU で ISO を起動してみる": "Try booting the ISO in QEMU",
    "配布された ISO を検証する": "Verify a distributed ISO",
    "プリセットの一覧を出す": "List the available presets",
    "ブラウザでレシピを編集する": "Edit the recipe in a browser",
    "ローカル Web UI を起動します。127.0.0.1 にだけ待ち受けます。": (
        "Start the local web UI. It listens on 127.0.0.1 only."
    ),
    "開くレシピファイル (省略すると新規)": (
        "Recipe file to open (omit to start a new one)"
    ),
    "待ち受けポート (既定: 8765。0 で空きポートを自動選択)": (
        "Listening port (default: 8765; 0 picks a free port)"
    ),
    "ブラウザを自動で開かない": "Do not open the browser automatically",
    "GUI を起動しました: {url}": "GUI started: {url}",
    "終了するときは Ctrl-C を押してください。": (
        "Press Ctrl-C to stop the GUI."
    ),
    "ブラウザを開けませんでした。上の URL を開いてください。": (
        "Could not open the browser. Open the URL above manually."
    ),
    "GUI を終了しました。": "GUI stopped.",
    "レシピが見つかりません: {path}": "Recipe not found: {path}",
    ".toml ファイルのパスを指定してください。": "Specify the path to a .toml file.",
    "GUI を起動できませんでした: {error}": "Could not start the GUI: {error}",
    "ポート番号が不正です: {port}": "Invalid port number: {port}",
    "0 から 65535 の範囲で指定してください。": (
        "Specify a number between 0 and 65535."
    ),
    "--port で別のポートを指定してください。": (
        "Specify a different port with --port."
    ),
    "色を付けない (ログに落とすとき)": "Disable colour (useful when logging)",
    "UI の言語。en か ja": "UI language: en or ja",
    "UI の言語。en か ja (既定: 環境変数 LANG / LC_ALL / FROSTED_LANG から自動判定)": (
        "UI language: en or ja "
        "(default: detected from LANG / LC_ALL / FROSTED_LANG)"
    ),
    "内部のコマンドも表示する": "Also show the commands being run",
    # ---- cli.py: コマンドの説明 ------------------------------------------
    "対話でレシピファイルを作ります。": "Create a recipe file interactively.",
    "レシピから live-build の設定ツリーを生成します。root 権限は不要で、生成物を目で確認したいときに便利です。": (
        "Generate the live-build configuration tree from a recipe. "
        "No root needed, and handy for inspecting the generated files."
    ),
    "レシピから ISO をビルドします。数十分かかることがあります。": (
        "Build an ISO from a recipe. This can take tens of minutes."
    ),
    "レシピの内容とビルド環境を確認して、問題を一覧で出します。": (
        "Check the recipe and the build environment and list any problems."
    ),
    "レシピを読み込んだ結果と、実際に渡される設定を表示します。": (
        "Show the parsed recipe and the settings that will actually be used."
    ),
    "live-build 一式が揃っているか、空き容量は足りるかを確認します。": (
        "Check that live-build and its dependencies are present "
        "and that there is enough free disk space."
    ),
    "ビルドの成果物を消します。既定ではキャッシュを残すので、次回のビルドが速いままです。": (
        "Remove build products. The cache is kept by default, "
        "so the next build stays fast."
    ),
    "ビルド済みの chroot に入って中身を直接確認・修正します。レシピに書きづらい調整を試すときに使います。": (
        "Open a shell in the built chroot to inspect and change it directly. "
        "Useful for tweaks that are awkward to express in a recipe."
    ),
    "ビルドした ISO を QEMU で起動します。USB に焼く前に確認できます。": (
        "Boot the built ISO in QEMU so you can check it before writing a USB stick."
    ),
    "ISO のチェックサムと署名を検証します。配布物を受け取った側が実行する想定のコマンドです。": (
        "Verify the checksum and signature of an ISO. "
        "This is the command the person receiving your image runs."
    ),
    "使えるプリセットの一覧です。": "The list of available presets.",
    # ---- cli.py: オプションの説明 ----------------------------------------
    "書き出すレシピのパス (既定: <名前>.toml)": (
        "Where to write the recipe (default: <name>.toml)"
    ),
    "用途プリセット (対話を一部省略します)": (
        "Use case preset (skips some of the questions)"
    ),
    "ISO の名前 (指定するとその質問を飛ばします)": (
        "ISO name (skips that question)"
    ),
    "ベースにする Debian": "Debian release to base on",
    "ベースにする Debian (testing/sid も選べます)": (
        "Debian release to base on (testing/sid are also available)"
    ),
    "アーキテクチャ": "Architecture",
    "既存のファイルを上書きする": "Overwrite an existing file",
    "最後の確認を飛ばす": "Skip the final confirmation",
    "開始前の確認を飛ばす": "Skip the confirmation before starting",
    "環境の事前確認を飛ばす": "Skip the environment checks",
    "ミラーへの到達確認をしない (プロキシ環境などで)": (
        "Do not check that the mirror is reachable (for proxy environments)"
    ),
    "ISO のコピー先を上書きする": "Override where the ISO is copied to",
    "ISO に GPG の分離署名を作る。配布するなら指定する (例: --sign ABCD1234 や --sign you@example.com)": (
        "Create a detached GPG signature for the ISO. "
        "Use this if you distribute the image (e.g. --sign ABCD1234)"
    ),
    "SHA256SUMS と build-info.json を作らない": (
        "Do not create SHA256SUMS and build-info.json"
    ),
    "生成したファイルの一覧を出さない": "Do not list the generated files",
    "キャッシュも含めて全部消す": "Remove everything, including the cache",
    "ネットワークの確認をしない": "Do not check network access",
    "root 権限のチェックをしない": "Do not check for root privileges",
    "ブートパラメータだけを出す": "Print only the boot parameters",
    "lb config に渡す引数だけを出す": "Print only the lb config arguments",
    "レシピファイル (TOML)": "Recipe file (TOML)",
    "レシピファイル (省略可)": "Recipe file (optional)",
    "検証する ISO ファイル": "The ISO file to verify",
    "チェックサムファイル (既定: ISO と同じ場所の <ISO名>.sha256)": (
        "Checksum file (default: <ISO name>.sha256 next to the ISO)"
    ),
    "署名ファイル (既定: ISO と同じ場所の <ISO名>.asc)": (
        "Signature file (default: <ISO name>.asc next to the ISO)"
    ),
    "名前を指定すると、そのプリセットの詳細を出します": (
        "Give a name to see the details of that preset"
    ),
    "chroot が無ければ bootstrap と chroot を実行してから入る": (
        "Run bootstrap and chroot first if there is no chroot yet"
    ),
    "起動する ISO (既定: レシピの出力先)": (
        "The ISO to boot (default: the recipe's output path)"
    ),
    "割り当てメモリ (既定: 2048)": "Memory to allocate, in MB (default: 2048)",
    "UEFI で起動する": "Boot in UEFI mode",
    "KVM を使わない (とても遅くなる)": "Do not use KVM (very slow)",
    "レシピ": "RECIPE",
    "名前": "Name",
    # ---- cli.py: 出力 ---------------------------------------------------
    "ビルド環境を診断します": "Checking the build environment",
    "レシピを確認します: {path}": "Checking the recipe: {path}",
    "ビルド環境を確認します": "Checking the build environment",
    "レシピの内容に問題はありません。": "The recipe looks fine.",
    "レシピに問題があります": "the recipe has problems",
    "エラー": "error",
    "警告": "warning",
    "生成物を確認してください。とくに {path}": (
        "Check the generated files, especially {path}"
    ),
    "{count} 個のファイルを {path} に生成しました。": (
        "Wrote {count} files to {path}."
    ),
    "次はこれでビルドします:": "Build it with:",
    "先に中身を確認したいときは:": "To inspect the settings first:",
    "設定を生成します": "Generating the configuration",
    "設定を {path} に生成しました。": "Wrote the configuration to {path}.",
    "lb config (設定の反映)": "lb config (applying the settings)",
    "lb build (ISO を組み立てます)": "lb build (assembling the ISO)",
    "この段階が一番長いです。中断したいときは Ctrl-C。": (
        "This is the longest stage. Press Ctrl-C to stop."
    ),
    "ISO を取り出します": "Collecting the ISO",
    "配布用の成果物を作ります": "Creating the release artifacts",
    "ビルドできました。": "Build finished.",
    "大きさ": "Size",
    "ログ": "Log",
    "検証用": "Checksum",
    "ビルド情報": "Build info",
    "署名": "Signature",
    "次はこれで起動を確認できます:": "Try booting it with:",
    "USB に焼くときは:": "To write it to a USB stick:",
    "  ※ /dev/sdX は必ず自分の環境に合わせて確認してください。間違えるとデータが消えます。": (
        "  NOTE: check that /dev/sdX is really your device. "
        "The wrong one will erase data."
    ),
    "配布するときは、ISO と一緒に次のファイルも渡してください:": (
        "When you distribute this, ship these files alongside the ISO:"
    ),
    "受け取った側はこうやって検証できます:": (
        "The person receiving it can verify it like this:"
    ),
    "--- ログの末尾 ---": "--- end of log ---",
    "--- ここまで ---": "--- end of log ---",
    "作業ディレクトリがありません: {path}": "No work directory: {path}",
    "掃除しました。キャッシュは残っているので次のビルドは速いです。": (
        "Cleaned. The cache is still there, so the next build will be fast."
    ),
    "ビルドの成果物を消します (キャッシュは残します)": (
        "Removing build products (keeping the cache)"
    ),
    "次のコマンドでビルドできます:": "Build it with:",
    # ---- cli.py: show ---------------------------------------------------
    "ブートパラメータ": "Boot parameters",
    "lb config に渡す引数": "Arguments passed to lb config",
    "パッケージ": "Packages",
    "ファイル": "Files",
    "スクリプト": "Scripts",
    "  追加: {packages}": "  Add: {packages}",
    "  追加: {line}": "  Add: {line}",
    "  鍵: {path}": "  Key: {path}",
    "  同梱: {path}": "  Bundle: {path}",
    "  壁紙 {path}": "  Wallpaper {path}",
    "  インストール先: {params}": "  Installed system: {params}",
    "  APT のピン留め: 設定あり": "  APT pinning: configured",
    "スワップファイル": "Swap file",
    "  {path} ({size} MB)": "  {path} ({size} MB)",
    "リポジトリ": "Repositories",
    "  除外: {packages}": "  Remove: {packages}",
    "  コピー  {source} -> {target}": "  copy    {source} -> {target}",
    "  書き込み {path}": "  write   {path}",
    "  ビルド時   {path}": "  build time  {path}",
    "  初回起動時 {path}": "  first boot  {path}",
    # ---- cli.py: presets ------------------------------------------------
    "使えるプリセット": "Available presets",
    "使い方: {command}": "Usage:  {command}",
    "詳細:   {command}": "Detail: {command}",
    "デスクトップ環境の選択肢:": "Desktop environments:",
    "知らないプリセットです: {name}": "Unknown preset: {name}",
    "選べるもの: {items}": "Choices: {items}",
    "    デスクトップ: {value}": "    Desktop:        {value}",
    "    自動ログイン: {value}": "    Autologin:      {value}",
    "    sudo:         {value}": "    sudo:           {value}",
    "    SSH:          {value}": "    SSH:            {value}",
    "    追加パッケージ:": "    Extra packages:",
    # ---- cli.py: verify -------------------------------------------------
    "検証します: {name}": "Verifying: {name}",
    "ISO が見つかりません: {path}": "ISO not found: {path}",
    "パスを確認してください。": "Check the path.",
    "チェックサムが一致しました ({digest})": "Checksum matches ({digest})",
    "チェックサムが一致しません。ファイルが壊れているか改ざんされています。": (
        "Checksum does NOT match. The file is corrupt or has been tampered with."
    ),
    "  期待値 {expected}": "  expected  {expected}",
    "  実際   {actual}": "  actual    {actual}",
    "チェックサムファイルがありません: {name}": "No checksum file: {name}",
    "チェックサムファイルを読めませんでした: {name}": (
        "Could not read the checksum file: {name}"
    ),
    "チェックサムファイルにこの ISO の行がありません: {name}": (
        "No entry for this ISO in the checksum file: {name}"
    ),
    "ISO だけを渡されている場合は検証できません。": (
        "If you were given only the ISO, it cannot be verified."
    ),
    "署名はありますが gpg が無いので検証できません。": (
        "There is a signature but gpg is not installed, so it cannot be checked."
    ),
    "署名を検証できました。": "Signature verified.",
    "署名の検証に失敗しました。": "Signature verification FAILED.",
    "配布元の公開鍵をインポートしてあるか確認してください。": (
        "Check that you have imported the publisher's public key."
    ),
    "署名ファイルはありません。": "No signature file.",
    "ビルド情報:": "Build info:",
    "作成元": "Publisher",
    "識別子": "Identifier",
    "バージョン": "Version",
    "ベース": "Based on",
    "ビルド日時": "Built at",
    "パッケージ数": "Package count",
    "検証に失敗しました。": "Verification failed.",
    "検証できました。": "Verified.",
    "検証できるものがありませんでした。": "There was nothing to verify against.",
    # ---- cli.py: clean / shell / test -----------------------------------
    "ビルドできました。": "Build finished.",
    "chroot がまだありません: {path}": "There is no chroot yet: {path}",
    "chroot が無いので先に用意します (少し時間がかかります)。": (
        "No chroot yet, so preparing one first (this takes a while)."
    ),
    "chroot に入ります。抜けるときは exit と入力してください。": (
        "Opening a shell in the chroot. Type exit to leave."
    ),
    "frosted test は今のところ amd64/i386 用です。": (
        "frosted test currently supports amd64/i386 only."
    ),
    "arm64 の ISO は実機か、qemu-system-aarch64 と AAVMF で起動してください。": (
        "Boot arm64 ISOs on real hardware or with qemu-system-aarch64 and AAVMF."
    ),
    "QEMU がインストールされていません。": "QEMU is not installed.",
    "UEFI 用のファームウェア (OVMF) が見つかりません。": (
        "UEFI firmware (OVMF) was not found."
    ),
    "起動します: {name}": "Booting: {name}",
    "終了するときは QEMU のウィンドウを閉じるか、Ctrl-A のあと X を押します。": (
        "To quit, close the QEMU window, or press Ctrl-A then X."
    ),
    "/dev/kvm が無いのでエミュレーションで起動します。とても遅くなります。": (
        "/dev/kvm is missing, so QEMU will emulate. This is very slow."
    ),
    "sudo apt install qemu-system-x86": "sudo apt install qemu-system-x86",
    "sudo apt install ovmf": "sudo apt install ovmf",
    # ---- wizard.py ------------------------------------------------------
    "Linux ISO Builder — 新しいレシピを作る": (
        "Frosted ISO Builder — create a new recipe"
    ),
    "質問に答えていくと、ビルド用のレシピファイルが 1 枚できます。": (
        "Answer a few questions and you will get a recipe file to build from."
    ),
    "括弧内が既定値です。そのまま使うなら {key} を押してください。": (
        "The value in brackets is the default. Press {key} to accept it."
    ),
    "いつでも {key} で中断できます。": "You can press {key} at any time to abort.",
    "1/8  ISO の名前": "1/8  ISO name",
    "2/8  ベースにする Debian": "2/8  Debian base",
    "3/8  用途": "3/8  Use case",
    "4/8  デスクトップ環境": "4/8  Desktop environment",
    "5/8  言語サポート": "5/8  Language support",
    "6/8  ユーザーとログイン": "6/8  User and login",
    "7/8  地域の設定": "7/8  Regional settings",
    "8/8  追加の設定": "8/8  Extra settings",
    "名前 (英小文字・ハイフン)": "Name (lowercase letters and hyphens)",
    "バージョン (ファイル名に入ります)": "Version (used in the file name)",
    "どのリリースをベースにしますか?": "Which Debian release should this be based on?",
    "Debian 13。現行の安定版。特におすすめ。": (
        "Debian 13. The current stable release. Recommended."
    ),
    "Debian 12。少し前の安定版。古いドライバが必要なとき。": (
        "Debian 12. The previous stable release. For older drivers."
    ),
    "Debian Testing。次の安定版の開発版。新しいパッケージが使えるが、壊れることがある。": (
        "Debian Testing. The development branch for the next stable release; "
        "newer packages, but things can break."
    ),
    "Debian Sid (unstable)。最先端だが動作保証はない。security ミラーは使わない。": (
        "Debian Sid (unstable). Bleeding edge with no guarantees; "
        "no security mirror is used."
    ),
    "64bit PC。通常はこれ。": "64-bit PC. Usually this one.",
    "32bit PC。よほど古いマシンでない限り不要。": (
        "32-bit PC. Unnecessary unless the machine is very old."
    ),
    "64bit ARM。Raspberry Pi 4 以降など。": (
        "64-bit ARM. Raspberry Pi 4 and later, for example."
    ),
    "どんな用途の ISO にしますか?": "What will this ISO be used for?",
    "デスクトップ環境": "Desktop environment",
    "追加の言語サポート": "Additional language support",
    "ライブ環境のユーザー名": "User name in the live system",
    "フルネーム (表示用)": "Full name (for display)",
    "起動時に自動でログインしますか?": "Log in automatically at boot?",
    "パスワード (空のままにするとログインできません)": (
        "Password (leave empty and you will not be able to log in)"
    ),
    "このユーザーに sudo (管理者権限) を許可しますか?": (
        "Allow this user to use sudo (administrator privileges)?"
    ),
    "自動ログインなのでパスワードは設定しません。": (
        "Autologin is on, so no password will be set."
    ),
    "パスワードも設定済みです (SSH やコンソールログインで使えます)。": (
        "A password is also set (usable for SSH and console login)."
    ),
    "追加で入れたいパッケージ (空白区切り、無ければ Enter)": (
        "Extra packages to install (space separated, or just press Enter)"
    ),
    "SSH サーバーを入れて、外からログインできるようにしますか?": (
        "Install an SSH server so you can log in remotely?"
    ),
    "SSH 公開鍵のファイル (空白区切り)": (
        "SSH public key files (space separated)"
    ),
    "公開鍵を指定していません。パスワード認証は既定で無効なので、このままだと SSH でログインできません。": (
        "No public keys given. Password authentication is off by default, "
        "so you would not be able to log in over SSH."
    ),
    "パスワードでの SSH ログインを許可しますか?": (
        "Allow SSH login with a password?"
    ),
    "詳細設定 (ミラー・圧縮方式・永続化) を変更しますか?": (
        "Change the advanced settings (mirror, compression, persistence)?"
    ),
    "APT ミラー": "APT mirror",
    "squashfs の圧縮方式": "squashfs compression",
    "壁紙の画像 (空なら変更しない)": (
        "Wallpaper image (leave empty to keep the default)"
    ),
    "圧縮率が高い。ビルドは遅い。既定。": (
        "Best compression. Slower to build. The default."
    ),
    "速くてそこそこ縮む。最近の傾向。": (
        "Fast, and compresses reasonably well. The modern choice."
    ),
    "最速だが大きい。とにかく速く作りたいとき。": (
        "Fastest but largest. For when you just want it built quickly."
    ),
    "非常に速いが大きい。試行錯誤向け。": (
        "Very fast but large. Useful while experimenting."
    ),
    "圧縮しない。開発中の試行錯誤向け。": (
        "No compression. For iterating during development."
    ),
    "ビルドキャッシュを残しますか? (2 回目以降が速くなります)": (
        "Keep the build cache? (makes later builds faster)"
    ),
    "永続化 (persistence) を有効にしますか? USB に変更を保存できますが、USB 側の準備が別途必要です。": (
        "Enable persistence? It saves your changes to the USB stick, "
        "but the stick needs to be prepared separately."
    ),
    "キオスクで表示する URL": "URL to show in the kiosk",
    "この内容で作ります": "This is what will be built",
    "この内容でレシピを保存しますか?": "Save the recipe with these settings?",
    "レシピを保存しました: {path}": "Saved the recipe: {path}",
    "やめました。別の名前を指定してください (--output)。": (
        "Cancelled. Choose a different name with --output."
    ),
    "保存しませんでした。": "Nothing was saved.",
    "{path} は既にあります。上書きしますか?": "{path} already exists. Overwrite it?",
    # ---- wizard.py: 要約の値 --------------------------------------------
    "出力ファイル": "Output file",
    "ユーザー": "User",
    "ログイン": "Login",
    "自動ログインあり": "autologin",
    "パスワード入力": "password required",
    "あり": "yes",
    "なし": "no",
    "有効": "enabled",
    "無効": "disabled",
    "{count} 個": "{count}",
    "ホスト名": "Hostname",
    "ロケール": "Locale",
    "タイムゾーン": "Timezone",
    "キーボード": "Keyboard",
    "追加パッケージ": "Extra packages",
    "作業ディレクトリ": "Work directory",
    "壁紙": "Wallpaper",
    "リポジトリの鍵": "Repository keys",
    "永続化": "Persistence",
    # ---- wizard.py: 検証メッセージ --------------------------------------
    "半角小文字・数字・ハイフンのみ。先頭と末尾はハイフン以外。例: my-linux": (
        "Lowercase letters, digits and hyphens only. "
        "Cannot start or end with a hyphen, e.g. my-linux"
    ),
    "半角小文字で始まり、小文字・数字・_・- のみ (32 文字以内)。": (
        "Must start with a lowercase letter; "
        "lowercase letters, digits, _ and - only (max 32)."
    ),
    "root は使えません。": "root is not allowed.",
    "半角小文字・数字・ハイフンのみ、63 文字以内。例: mylinux": (
        "Lowercase letters, digits and hyphens only, max 63, e.g. mylinux"
    ),
    "半角英数字と . _ + ~ - のみ。空白や / は使えません。": (
        "Only ASCII letters, digits and . _ + ~ - are allowed; "
        "spaces and / are not."
    ),
    "コロンと改行は使えません。": "Colons and newlines are not allowed.",
    "0 以上で指定してください。": "Specify 0 or greater.",
    "1 以上で指定してください。": "Specify 1 or greater.",
    "開発版 (testing/sid) です。"
    "ビルドや起動が壊れることがあります。": (
        "This is a development release (testing/sid). "
        "The build or boot may break."
    ),
    "安定版が必要なら trixie を使ってください。": (
        "Use trixie if you need a stable release."
    ),
    "sid/unstable には security アーカイブがありません。"
    "build.security_mirror は使用しません。": (
        "sid/unstable has no security archive; "
        "build.security_mirror will not be used."
    ),
    "security 更新は unstable 経由で入ります。": (
        "Security updates arrive through unstable."
    ),
    "インストーラーが none のため、preseed は使われません。": (
        "The installer type is none, so the preseed file is not used."
    ),
    "インストーラーが none のため、install_append は使われません。": (
        "The installer type is none, so install_append is not used."
    ),
    "インストーラーが none のため、firmware_binary は使われません。": (
        "The installer type is none, so firmware_binary is not used."
    ),
    "swap_file_path が未設定なので、サイズは使われません。": (
        "swap_file_path is not set, so the size is not used."
    ),
    '例: swap_file_path = "/swapfile"': 'Example: swap_file_path = "/swapfile"',
    "1 以上 (MB) で指定してください。": "Specify 1 or greater (MB).",
    "イメージ内の絶対パスで書いてください。": (
        "Use an absolute path inside the image."
    ),
    ".. は使えません。": ".. is not allowed.",
    "空白や引用符は使えません。": "Spaces and quotes are not allowed.",
    "ファイル名まで含めてください。": "Include a file name.",
    "空白や引用符を含まない .deb にしてください。": (
        "Use a .deb file name without spaces or quotes."
    ),
    "dpkg-deb が作る元のファイル名のまま置いてください。": (
        "Keep the original file name produced by dpkg-deb."
    ),
    "config/packages.chroot/ に同じ名前で置かれるためです。": (
        "They are placed in config/packages.chroot/ with the same name."
    ),
    "NUL 文字は使えません。": "NUL characters are not allowed.",
    "デスクトップ環境が none のため、壁紙は設定されません。": (
        "The desktop environment is none, so the wallpaper is not applied."
    ),
    "KDE では壁紙の自動設定に対応していません。"
    "画像はイメージ内にコピーされます。": (
        "KDE wallpaper is not set automatically; "
        "the image is copied into the image."
    ),
    "KDE では手動で壁紙を設定してください。": (
        "Set the wallpaper manually in KDE."
    ),
    "半角英数字・._- のみにしてください。": (
        "Use only ASCII letters, digits, ., _ and -."
    ),
    "イメージ内で /usr/share/keyrings/ に同じ名前で置かれるためです。": (
        "They are copied into /usr/share/keyrings/ with the same name."
    ),
    "拡張子を変えただけの同名ファイルは config/archives/ で衝突します。": (
        "Files with the same base name but a different extension collide "
        "in config/archives/."
    ),
    # ---- recipe.py: 旧フィールド名の移行 ---------------------------------
    "Keychrom は owner の旧名です。": "Keychrom is an old name for owner.",
    "owner に書き換えてください。": "Please rename it to owner.",
    "owner と Keychrom は同時に指定できません。": (
        "owner and Keychrom cannot be used together."
    ),
    "Keychrom は旧名です。owner だけを使ってください。": (
        "Keychrom is an old name; use owner only."
    ),
    "作業ディレクトリが空か、改行を含んでいます。": (
        "The work directory is empty or contains a newline."
    ),
    "レシピの下の build など、通常のディレクトリ名を指定してください。": (
        "Specify a normal directory name such as build under the recipe."
    ),
    "build.workdir がレシピのあるディレクトリやその親、"
    "ホーム、ルートを指していないか確認してください。": (
        "Check that build.workdir does not point to the recipe directory, "
        "one of its parents, your home directory, or the filesystem root."
    ),
    "live-build は空白を含むパスではビルドできません。"
    " build.workdir を空白の無い場所に変更してください。": (
        "live-build cannot build in a path containing spaces. "
        "Change build.workdir to a location without spaces."
    ),
    "build.workdir を build など、レシピの下のディレクトリに変更してください。": (
        "Change build.workdir to a directory under the recipe, such as build."
    ),
    "Windows ではビルドしないため確認しません": (
        "Skipped because the build does not run on Windows."
    ),
    # ---- livebuild.py / recipe.py: arm64 のブートローダ ----------------
    "arm64 では x86 用のブートローダ "
    "(syslinux/grub-pc/grub-legacy) が使えません。除外されます。": (
        "x86 bootloaders (syslinux/grub-pc/grub-legacy) cannot be used on "
        "arm64; they will be dropped."
    ),
    "arm64 は grub-efi のみを使います。": "arm64 uses grub-efi only.",
    "arm64 では x86 用のブートローダ "
    "(syslinux/grub-pc/grub-legacy) を除外しました。": (
        "Dropped x86 bootloaders (syslinux/grub-pc/grub-legacy) on arm64."
    ),
    "arm64 では grub-efi を使います。": "Using grub-efi on arm64.",
    "ブートローダが空だったので grub-efi を使います。": (
        "No bootloader was specified; using grub-efi."
    ),
    "例: Asia/Tokyo / Europe/Berlin / UTC": "e.g. Asia/Tokyo, Europe/Berlin, UTC",
    "例: ja_JP.UTF-8 / en_US.UTF-8 / C.UTF-8": (
        "e.g. ja_JP.UTF-8, en_US.UTF-8, C.UTF-8"
    ),
    "このマシンに /usr/share/zoneinfo/{zone} がありません。綴りを確認してください。": (
        "This machine has no /usr/share/zoneinfo/{zone}. Check the spelling."
    ),
    # ---- cli.py: その他 -------------------------------------------------
    "Python 3.11 以上が必要です (今は {version})。": (
        "Python 3.11 or newer is required (found {version})."
    ),
    "TOML を読むために標準ライブラリの tomllib を使っています。": (
        "The standard library's tomllib is used to read TOML."
    ),
    "ファイル操作に失敗しました: {error}": "File operation failed: {error}",
    "中断しました。": "Aborted.",
    "やめました。": "Cancelled.",
    "完了しました。": "Done.",

    # ---- 自動ログインのフックとキオスク --------------------------------
    '    echo "frosted: lightdm が見つかりません。自動ログインは設定されません。" >&2': '    echo "frosted: lightdm not found. Autologin will not be configured." >&2',
    '    echo "frosted: sddm が見つかりません。自動ログインは設定されません。" >&2': '    echo "frosted: sddm not found. Autologin will not be configured." >&2',
    '    echo "frosted: gdm3 が見つかりません。自動ログインは設定されません。" >&2': '    echo "frosted: gdm3 not found. Autologin will not be configured." >&2',
    '# キオスクモードで Chromium を起動する。URL は /etc/kiosk-url から読む。': '# Start Chromium in kiosk mode. The URL is read from /etc/kiosk-url.',
    '# 画面の消灯とスクリーンセーバーを止める': '# Stop the screen from blanking and the screensaver from running',
    '# マウスカーソルを一定時間で隠す': '# Hide the mouse cursor after a short idle',
    'Comment=キオスクブラウザを自動起動する': 'Comment=Start the kiosk browser automatically',

    # ---- フックの用途 (livebuild.py) ------------------------------------
    'システム設定': 'System settings',
    '自動ログイン設定': 'Autologin',
    'sudo 設定': 'sudo',
    'SSH 設定': 'SSH',
    'パーミッション設定': 'File permissions',
    '起動時の設定': 'Boot-time setup',
    '利用者のセットアップスクリプト': 'User setup scripts',
    '除外パッケージの削除': 'Removing excluded packages',
    '後片付け': 'Cleanup',

    # ---- 生成するファイルの中身 (livebuild.py) --------------------------
    '# 設定を変えたいときはレシピ (*.toml) を直して `frosted gen` を再実行します。': '# To change the settings, edit the recipe (*.toml) and run `frosted gen` again.',
    '# noauto は必須です。外すと live-build が auto/config を呼び続けて再帰します。': '# noauto is required. Without it live-build keeps calling auto/config and recurses.',
    '# 値は 1 つずつ shlex.quote で囲んであるので、空白入りの値もそのまま渡ります。': "# Every value is shlex.quote'd, so values containing spaces are passed intact.",
    '# 変更したいときはレシピ (*.toml) を直して `frosted gen` を再実行します。': '# To change anything, edit the recipe (*.toml) and run `frosted gen` again.',
    '# --- ロケール ---': '# --- locale ---',
    '    # 該当行のコメントを外す。見つからなければ何も起きない。': '    # Uncomment the matching line. Does nothing if it is not found.',
    '# --- タイムゾーン ---': '# --- timezone ---',
    '    echo "frosted: タイムゾーンが見つかりません: ${TIMEZONE}" >&2': '    echo "frosted: timezone not found: ${TIMEZONE}" >&2',
    '# --- キーボード ---': '# --- keyboard ---',
    '# --- ホスト名 ---': '# --- hostname ---',
    '# ライブユーザーはパスワードなしで sudo できる。': '# The live user can use sudo without a password.',
    '# 書式が壊れていると sudo が全く使えなくなるので、ここで検証しておく': '# A broken file would disable sudo entirely, so check it here.',
    '# 公開鍵はレシピで指定されていない。パスワード認証が無効なら SSH ログインできない。': '# No public keys in the recipe. With password auth off, SSH login is impossible.',
    '# --- 起動時の設定スクリプト ---': '# --- boot-time setup script ---',
    '# root のパスワードなどが入るので、ライブユーザーからは読めないようにする。': '# Contains the root password, so keep it unreadable to the live user.',
    '# systemd は root で実行するため 0700 でも動く。': '# systemd runs it as root, so mode 0700 is fine.',
    '# live-config がライブユーザーを作ったあとに 1 度だけ実行されます。': '# Runs once, after live-config has created the live user.',
    '# すべての操作は何度実行しても同じ結果になるように書いています。': '# Every step is written to be idempotent.',
        "# [daemon] セクションに自動ログインの設定を足す": "# Add autologin settings to the [daemon] section",
    '# --- フルネーム ---': '# --- full name ---',
    'log "フルネームを設定しました。"': 'log "set the user full name."',
    'log "フルネームを設定できませんでした。"': 'log "failed to set the user full name."',
    '# --- 自動ログイン ---': '# --- autologin ---',
'# --- 自動ログイン用グループ ---': '# --- group for autologin ---',
    '# --- ライブユーザーができるのを待つ ---': '# --- wait for the live user ---',
    '# このユニットは After=live-config.service で順序を指定しているが、': '# This unit sets After=live-config.service, but',
    '# ユニット名が違う環境では順序が効かず、ユーザー作成より先に走りうる。': '# where the unit is named differently that ordering has no effect and this',
    '# その場合は黙って諦めず、少しの間待ってからやり直す。': '# may run before the user exists. Rather than giving up silently, wait and retry.',
    '    log "ユーザー ${USERNAME} が 30 秒待っても見つかりません。"': '    log "user ${USERNAME} still missing after 30 seconds."',
    '    log "live-config がユーザーを作れなかった可能性があります。次のコマンドで確認してください:"': '    log "live-config may have failed to create it. Check with:"',
    '# --- 追加のグループ ---': '# --- extra groups ---',
    '# --- ライブユーザーのパスワード ---': '# --- live user password ---',
    'log "ライブユーザーのパスワードを設定しました。"': 'log "set the live user password."',
    '# chroot 内でも確実に効くよう、enable は systemctl ではなく直接シンボリックリンクで行う': '# Enable by creating the symlink directly: systemctl is unreliable inside a chroot.',
    '# 名指しされたパッケージだけを削除する。依存関係の自動削除はしない。': '# Remove only the named packages. No dependency-following autoremove.',
    '# APT のキャッシュとリスト': '# APT caches and lists',
    '# machine-id はコピー間で共有されると問題になるので消す。': '# Remove machine-id: sharing it between copies causes problems.',
    '# systemd が初回起動時に作り直す。': '# systemd regenerates it on first boot.',
    '# ビルド中にできたログ': '# Logs produced during the build',
    '# シェルの履歴': '# Shell history',
    '# 一時ファイル': '# Temporary files',
    '# このディレクトリについて': '# About this directory',
    '**生成されたファイルを直接編集しないでください。** 次に生成したときに上書きされます。': '**Do not edit the generated files directly.** They are overwritten next time.',
    '設定を変えたいときはレシピファイルを直して、次のコマンドを実行してください。': 'To change the settings, edit the recipe file and run:',
    '## 手でビルドする': '## Building by hand',
    'このツールを経由せず live-build を直接叩くこともできます。': 'You can also call live-build directly, without going through frosted.',
    '`auto/config` が置いてあるので、`lb build` は自動的にレシピどおりの設定で': '`auto/config` is in place, so `lb build` automatically uses the settings',
    'コピーされます (このツール経由の場合)。': 'is copied next to the recipe (when built through frosted).',
    '## 掃除': '## Cleaning up',
    'sudo lb clean          # ビルド成果物だけ消す (キャッシュは残る)': 'sudo lb clean          # remove build products (cache is kept)',
    'sudo lb clean --purge  # 設定も含めて全部消す': 'sudo lb clean --purge  # remove everything, including the settings',
    '## 設定の対応表': '## Where everything lives',
    '| どこ | 何が入っているか |': '| Path | What is in it |',
    '| `auto/config` | `lb config` に渡す全オプション。ここが実質の設定本体 |': '| `auto/config` | Every option passed to `lb config`. The real settings live here |',
    '| `config/package-lists/` | 入れるパッケージ (番号順に読み込まれる) |': '| `config/package-lists/` | Packages to install (read in numeric order) |',
    '| `config/packages.chroot/` | 同梱するローカル .deb (依存関係ごと導入される) |': '| `config/packages.chroot/` | Local .deb files to bundle (installed with dependencies) |',
    '| `config/includes.chroot/` | イメージにそのまま入れるファイル |': '| `config/includes.chroot/` | Files copied into the image as-is |',
    '| `config/hooks/live/` | ビルド中に chroot 内で走るスクリプト。番号順 |': '| `config/hooks/live/` | Scripts run inside the chroot during the build, in numeric order |',
    '| `config/archives/` | 追加の APT リポジトリ |': '| `config/archives/` | Extra APT repositories |',
    '| `config/archives/frosted.pref` | APT のピン留め |': '| `config/archives/frosted.pref` | APT pinning |',
    '| `.frosted-manifest.json` | このツールが生成したファイルの一覧 (掃除に使う) |': '| `.frosted-manifest.json` | List of files frosted generated (used for cleanup) |',
    '## ブートパラメータ': '## Boot parameters',
    'failsafe エントリ:': 'failsafe entry:',
    # ---- 診断項目の名前 (`preflight.py`) --------------------------------
    """例:
  # 対話でレシピを作って、そのままビルドする
  frosted init
  sudo frosted build mylinux.toml

  # 設定だけ生成して中身を確認する (root 不要)
  frosted gen mylinux.toml
  frosted show mylinux.toml

  # 環境に何が足りないか調べる
  frosted doctor

くわしくは README.md を見てください。
""": (
        """Examples:
  # Create a recipe interactively, then build it
  frosted init
  sudo frosted build mylinux.toml

  # Generate the configuration only and inspect it (no root needed)
  frosted gen mylinux.toml
  frosted show mylinux.toml

  # Check what is missing on this machine
  frosted doctor

See README.md for the full documentation.
"""
    ),
    "OS": "OS",
    "権限": "Privileges",
    "必須ツール": "Required tools",
    "任意ツール": "Optional tools",
    "アーキテクチャ": "Architecture",
    "空き容量": "Free disk space",
    "ミラー": "Mirror",
    "lb オプション": "lb options",
    # ---- 残りのメッセージ ----------------------------------------------
    "コマンド": "COMMAND",
    "デスクトップ環境が none なので、自動ログインはコンソール (tty) にのみ効きます。": (
        "The desktop environment is none, so autologin only applies "
        "to the console (tty)."
    ),
    "半角小文字・数字・ハイフンのみ。先頭と末尾はハイフン以外。例: my-linux-1": (
        "Lowercase letters, digits and hyphens only. "
        "Cannot start or end with a hyphen, e.g. my-linux-1"
    ),
    "live-build に並列度を指定するオプションが無いため削除しました。": (
        "Removed: live-build has no option to set the job count."
    ),
    "`frosted init` で新しく作れます。": "Create one with `frosted init`.",
    "このプリセットに含まれるパッケージ:": "What this preset includes:",
    "    sudo:         {value}": "    sudo:           {value}",
    "    SSH:          {value}": "    SSH:            {value}",
    "{label} ({key})": "{label} ({key})",
    "既存のファイルがあります。上書きしますか?": "The file already exists. Overwrite it?",
    "レシピを保存しますか?": "Save the recipe?",
}

# --------------------------------------------------------------------------
# 「前置き: 値」形式の前置き部分
# --------------------------------------------------------------------------

#: 値の部分には触らず、前置きだけを差し替える。
#: 検証メッセージの大半がこの形なので、ここだけでほとんど片付く。
PREFIXES: dict[str, str] = {
    # 検証 (`recipe.py`)
    "ISO の名前は必須です。": "The ISO name is required.",
    "使えない名前です": "Invalid name:",
    "使えないバージョンです": "Invalid version:",
    "壁紙の画像が見つかりません": "Wallpaper image not found:",
    "画像が見つかりません": "Image not found:",
    "壁紙に使えない形式です": "Unsupported wallpaper format:",
    "リポジトリの鍵が見つかりません": "Repository key not found:",
    "preseed ファイルが見つかりません": "Preseed file not found:",
    "未対応の APT バックエンドです": "Unsupported APT backend:",
    "未対応のインストーラー種別です": "Unsupported installer type:",
    "未対応の debconf frontend です": "Unsupported debconf frontend:",
    "未対応の debconf priority です": "Unsupported debconf priority:",
    "使えないリリース名です": "Invalid release name:",
    "使えないフレーバー名です": "Invalid kernel flavour:",
    "鍵のファイル名に使えない文字があります": (
        "Invalid repository key file name:"
    ),
    "鍵の形式が不明です": "Unknown key file format:",
    "同じ名前の鍵が複数あります": "Duplicate repository key file name:",
    "同じベース名の鍵が複数あります": (
        "Duplicate repository key base name:"
    ),
    "使える形式": "Supported formats:",
    "対応": "Supported:",
    "この作業ディレクトリは削除できません": (
        "Refusing to delete this work directory:"
    ),
    "空白を含みます": "contains a space:",
    "ルートディレクトリを指しています": "points at the filesystem root:",
    "使えないラベルです": "Invalid label:",
    "使えないホスト名です": "Invalid hostname:",
    "使えないロケールです": "Invalid locale:",
    "使えないタイムゾーンです": "Invalid timezone:",
    "使えないキーボード配列です": "Invalid keyboard layout:",
    "使えないユーザー名です": "Invalid user name:",
    "使えないパーミッションです": "Invalid permission mode:",
    "使えない文字が入っています": "Contains characters that are not allowed:",
    "知らない設定項目です": "Unknown setting:",
    "知らないデスクトップ環境です": "Unknown desktop environment:",
    "知らないプリセットです": "Unknown preset:",
    "知らないアーカイブ領域です": "Unknown archive area:",
    "未対応のアーキテクチャです": "Unsupported architecture:",
    "未対応の圧縮方式です": "Unsupported compression:",
    "未対応の値です": "Unsupported value:",
    "未対応のブートローダです": "Unsupported bootloader:",
    "動作確認していないリリースです": "Untested Debian release:",
    "パッケージ名として不正です": "Not a valid package name:",
    "このツールが対応していないレシピバージョンです": "Unsupported recipe version:",
    "この live-build はオプションに対応していないため、設定は反映されません。": (
        "This live-build does not support the option, so the setting is ignored."
    ),
    "スクリプトが見つかりません": "Script not found:",
    "コピー元が見つかりません": "Source not found:",
    "公開鍵が見つかりません": "Public key not found:",
    "探した場所": "Looked in:",
    "ミラー URL が不正です": "Invalid mirror URL:",
    "プロキシ URL が不正です": "Invalid proxy URL:",
    "レシピファイルが見つかりません": "Recipe file not found:",
    "レシピファイルを読めません": "Cannot read the recipe file:",
    "レシピファイルが UTF-8 ではありません": "The recipe file is not UTF-8:",
    "レシピファイルの TOML 構文に誤りがあります": (
        "The recipe file has a TOML syntax error:"
    ),
    "該当箇所を確認してください": "Check this file:",
    "このツールが対応していないレシピバージョンです。": (
        "Unsupported recipe version."
    ),
    "このマシンに": "This machine has no",
    "がありません。綴りを確認してください。": "Check the spelling.",
    # 実行 (`runner.py`, `release.py`, `cli.py`)
    "コマンドが見つかりません": "Command not found:",
    "コマンドを実行できません": "Cannot run the command:",
    "署名に失敗しました (終了コード": "Signing failed (exit code",
    "鍵": "Check that the key",
    "が秘密鍵として存在するか確認してください: gpg --list-secret-keys": (
        "exists as a secret key: gpg --list-secret-keys"
    ),
    "レシピを読み込めません": "Cannot load the recipe:",
    # `preflight.py`
    "見つかりません": "not found:",
    "確認できません": "cannot check:",
    "確認できませんでした": "could not check:",
    "次を実行してください: sudo apt install": (
        "Install them with: sudo apt install"
    ),
    "到達できます": "reachable:",
    "ホストと同じです": "same as the host:",
    "上の [x] の項目を解消してから、もう一度実行してください。": (
        "Fix the items marked [x] above and run it again."
    ),
    # 共通
    "例": "e.g.",
    "次を実行してください": "Install them with:",
    "対応": "Supported:",
    "確認済み": "Verified:",
    "選べるもの": "Choices:",
    "ログ": "Log:",
    "ログ全体": "Full log:",
    "ヒント": "Hint:",
}

# --------------------------------------------------------------------------
# 型にはまらない文 (正規表現)
# --------------------------------------------------------------------------

#: 数値やパスが混ざるなど、前置き方式で拾えない文。上から順に試す。
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^未対応の init システムです: (?P<value>.+)$"),
        r"Unsupported init system: \g<value>",
    ),
    (
        re.compile(r"^未対応の initramfs です: (?P<value>.+)$"),
        r"Unsupported initramfs: \g<value>",
    ),
    (
        re.compile(r"^パッケージが見つかりません: (?P<path>.+)$"),
        r"Package not found: \g<path>",
    ),
    (
        re.compile(
            r"^パッケージのファイル名が _all\.deb でも "
            r"_(?P<arch>.+?)\.deb でもありません: (?P<name>.+)$"
        ),
        r"The package file name is neither _all.deb nor "
        r"_\g<arch>.deb: \g<name>",
    ),
    (
        re.compile(r"^ファイル名に使えない文字があります: (?P<name>.+)$"),
        r"The file name contains unsupported characters: \g<name>",
    ),
    (
        re.compile(r"^同じ名前のパッケージが複数あります: (?P<name>.+)$"),
        r"Multiple packages have the same name: \g<name>",
    ),
    (
        re.compile(r"^# X セッション: (?P<session>.+) \(ブートパラメータで指定済み\)$"),
        r"# X session: \g<session> (set via boot parameter)",
    ),
    (re.compile('^# (?P<who>.+?) がレシピから生成しました。手で編集しないでください。$'), '# Generated by \\g<who> from the recipe. Do not edit by hand.'),
    (re.compile('^# (?P<who>.+?) が生成しました \\((?P<what>.+?)\\)。手で編集しないでください。$'), '# Generated by \\g<who> (\\g<what>). Do not edit by hand.'),
    (re.compile('^# (?P<who>.+?) が生成しました。$'), '# Generated by \\g<who>.'),
    (re.compile('^`(?P<who>.+?)` がレシピから生成した live-build の作業ディレクトリです。$'), 'The live-build work directory generated from the recipe by `\\g<who>`.'),
    (re.compile('^動きます。生成される ISO は `(?P<name>.+?)` としてレシピと同じディレクトリに$'), 'takes effect. The resulting ISO, `\\g<name>`, is'),
    (re.compile('^    log \\"グループ (?P<name>.+?) を作れませんでした。\\"$'), '    log "could not create group \\g<name>."'),
    (
        re.compile(r"^(?P<size>[\d.]+) GiB 空き \((?P<path>.+)\)$"),
        r"\g<size> GiB free (\g<path>)",
    ),
    (
        re.compile(r"^最低 (?P<min>\d+) GiB、快適に作るなら (?P<rec>\d+) GiB 以上必要です。$"),
        r"At least \g<min> GiB is needed; \g<rec> GiB or more is recommended.",
    ),
    (
        re.compile(r"^デスクトップ入りのイメージだと足りなくなることがあります。(?P<n>\d+) GiB 以上を確保するのを勧めます。$"),
        r"An image with a desktop environment may not fit. "
        r"Aim for at least \g<n> GiB.",
    ),
    (re.compile(r"^(?P<n>\d+) 個すべて見つかりました$"), r"all \g<n> found"),
    (re.compile(r"^(?P<n>\d+) 個すべて対応しています$"), r"all \g<n> supported"),
    (
        re.compile(r"^ホストは (?P<host>.+) ですが (?P<target>.+) を作ろうとしています$"),
        r"The host is \g<host> but you are building \g<target>",
    ),
    (
        re.compile(r"^HTTP (?P<code>\d+) が返りました: (?P<url>.+)$"),
        r"HTTP \g<code> returned for \g<url>",
    ),
    (
        re.compile(r"^(?P<n>\d+) 個のファイルを (?P<path>.+) に生成しました。$"),
        r"Wrote \g<n> files to \g<path>.",
    ),
]
