#!/bin/sh
# Frosted ISO Builder を Debian マシンにインストールする。
#
#   ./install.sh                        本体だけ入れる (依存は自分で入れる)
#   ./install.sh --with-deps            ビルドに必要なパッケージも apt で入れる
#   ./install.sh --with-additional      任意ツール (QEMU/OVMF, zsync, apt-cacher-ng) も入れる
#   ./install.sh --with-deps --with-additional
#                                       必須と任意をまとめて入れる
#   ./install.sh --uninstall            入れたものを消す (apt のパッケージは消さない)
#
# --with-deps / --with-additional は root で実行してください。
# PREFIX を変えるとインストール先を変更できます (既定: /usr/local)。

set -eu

usage() {
    cat <<'USAGE_EOF'
Frosted ISO Builder を Debian マシンにインストールする。

  ./install.sh                         本体だけ入れる (依存は自分で入れる)
  ./install.sh --with-deps             ビルドに必要なパッケージも apt で入れる
  ./install.sh --with-additional       任意ツール (QEMU/OVMF, zsync, apt-cacher-ng) も入れる
  ./install.sh --with-deps --with-additional
                                       必須と任意をまとめて入れる
  ./install.sh --uninstall             入れたものを消す (apt のパッケージは消さない)

--with-deps / --with-additional は root で実行してください。
PREFIX を変えるとインストール先を変更できます (既定: /usr/local)。
USAGE_EOF
}

PREFIX="${PREFIX:-/usr/local}"
LIBDIR="$PREFIX/lib/frosted"
BINDIR="$PREFIX/bin"

# ビルドに必要なパッケージ。live-build 自体が依存で引っ張るものも多いが、
# BIOS/UEFI 両対応のためにブートローダ一式を明示しておく。
# arm64 には grub-efi-amd64-bin が無いので、ホストのアーキテクチャに
# 合わせて選ぶ。ここを固定すると arm64 で --with-deps が失敗する。
HOST_ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$HOST_ARCH" in
    arm64|aarch64)
        BOOTLOADER_PACKAGES="grub-efi-arm64-bin"
        ;;
    i386|i686)
        BOOTLOADER_PACKAGES="syslinux-common isolinux grub-efi-ia32-bin grub-pc-bin"
        ;;
    *)
        BOOTLOADER_PACKAGES="syslinux-common isolinux grub-efi-amd64-bin grub-pc-bin"
        ;;
esac

DEPS="live-build debootstrap xorriso squashfs-tools cpio rsync uuid-runtime \
mtools dosfstools $BOOTLOADER_PACKAGES fakeroot gnupg"

# 無くてもビルドできるが、あると便利なもの。
# doctor の「任意ツール」と、frosted test --uefi が使う OVMF に対応する。
ADDITIONAL_PACKAGES="qemu-system-x86 ovmf zsync apt-cacher-ng"

WITH_DEPS=0
WITH_ADDITIONAL=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --with-deps) WITH_DEPS=1 ;;
        --with-additional) WITH_ADDITIONAL=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "知らないオプションです: $arg" >&2
            echo "使い方は ./install.sh --help を見てください。" >&2
            exit 1
            ;;
    esac
done

if [ "$UNINSTALL" = "1" ]; then
    echo "アンインストールします..."
    rm -rf "$LIBDIR"
    rm -f "$BINDIR/frosted"
    echo "完了しました。"
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$REPO_ROOT/frosted/cli.py" ]; then
    echo "エラー: このスクリプトはリポジトリのルートで実行してください。" >&2
    exit 1
fi

if [ "$WITH_DEPS" = "1" ] || [ "$WITH_ADDITIONAL" = "1" ]; then
    if [ "$(id -u)" != "0" ]; then
        echo "エラー: --with-deps / --with-additional は root で実行してください" >&2
        echo "       sudo ./install.sh --with-deps --with-additional" >&2
        exit 1
    fi

    PACKAGES=""
    if [ "$WITH_DEPS" = "1" ]; then
        PACKAGES="$DEPS"
    fi
    if [ "$WITH_ADDITIONAL" = "1" ]; then
        if [ -n "$PACKAGES" ]; then
            PACKAGES="$PACKAGES $ADDITIONAL_PACKAGES"
        else
            PACKAGES="$ADDITIONAL_PACKAGES"
        fi
    fi

    echo "パッケージを入れます..."
    # shellcheck disable=SC2086
    apt-get update
    # shellcheck disable=SC2086
    apt-get install -y $PACKAGES
fi

if [ "$(id -u)" = "0" ]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "エラー: $PREFIX に書き込むには root 権限が必要です。" >&2
        echo "       root で実行するか、sudo を入れてください。" >&2
        exit 1
    fi
fi

echo "インストール先: $LIBDIR"
$SUDO mkdir -p "$LIBDIR" "$BINDIR"

# ソースをコピーする。Python のキャッシュは持っていかない。
$SUDO rm -rf "$LIBDIR/frosted"
$SUDO cp -r "$REPO_ROOT/frosted" "$LIBDIR/frosted"
$SUDO find "$LIBDIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

LAUNCHER="$(mktemp)"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env python3
import sys

sys.path.insert(0, "$LIBDIR")

from frosted.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
LAUNCHER_EOF
$SUDO install -m 0755 "$LAUNCHER" "$BINDIR/frosted"
rm -f "$LAUNCHER"

echo "完了しました。"
echo
echo "動作確認:"
"$BINDIR/frosted" --version
echo
echo "次は環境を診断してみてください:"
echo "  frosted doctor"
