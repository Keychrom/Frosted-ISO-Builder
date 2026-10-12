"""公開用のリリース成果物を作る。

ISO を配布するときは、イメージ本体だけでは足りない。受け取った人が
「これは本当にその配布元が作ったものか」「中身は何か」を確かめられる
必要がある。ここではそのための 3 つを用意する。

- `SHA256SUMS` と `<ISO名>.sha256` … 破損や改ざんの検出
- `<ISO名>.build-info.json` … 何をどうやって作ったかの記録
- `<ISO名>.asc` … GPG による分離署名 (指定したときだけ)

どれも ISO の隣に置くだけなので、そのまま GitHub Releases に添付できる。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, GENERATED_BY, PROJECT_NAME
from .errors import BuildError
from .recipe import Recipe
from .runner import run_streaming

#: ハッシュを計算するときの読み込み単位。大きい ISO を丸ごと読まないため。
_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """ファイルの SHA-256 を求める。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ReleaseArtifacts:
    """生成した成果物の場所。"""

    iso: Path
    sha256: str = ""
    checksum_files: list[Path] = field(default_factory=list)
    build_info: Path | None = None
    signature: Path | None = None


# --------------------------------------------------------------------------
# チェックサム
# --------------------------------------------------------------------------


def write_checksums(iso_path: Path, digest: str) -> list[Path]:
    """ISO の隣にチェックサムを書く。

    2 種類作る。`<ISO名>.sha256` は単体で配る用、`SHA256SUMS` は
    `sha256sum -c` でまとめて検証できる慣習的な形式。
    """
    name = iso_path.name
    single = iso_path.with_name(f"{name}.sha256")
    single.write_text(f"{digest}  {name}\n", encoding="utf-8", newline="\n")

    combined = iso_path.with_name("SHA256SUMS")
    line = f"{digest}  {name}\n"
    if combined.exists():
        # 既に他の ISO の行があれば、その ISO の行だけ差し替える
        existing = combined.read_text(encoding="utf-8", errors="replace")
        lines = [
            old for old in existing.splitlines() if not old.endswith(f"  {name}")
        ]
        lines.append(line.rstrip("\n"))
        combined.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    else:
        combined.write_text(line, encoding="utf-8", newline="\n")

    return [single, combined]


# --------------------------------------------------------------------------
# ビルド情報
# --------------------------------------------------------------------------

_STATUS_RE = re.compile(r"^Status:\s*install ok installed$", re.MULTILINE)


def _installed_packages(chroot_dir: Path) -> list[dict[str, str]]:
    """ビルド後の chroot から、実際に入ったパッケージを拾う。

    配布物の透明性のために入れておく。chroot が残っていない (掃除済みなど)
    場合は空を返す。取れなくてもビルド自体は成功なので致命的にはしない。
    """
    status = chroot_dir / "var" / "lib" / "dpkg" / "status"
    if not status.is_file():
        return []

    try:
        text = status.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    packages: list[dict[str, str]] = []
    for block in text.split("\n\n"):
        if not _STATUS_RE.search(block):
            continue
        name = ""
        version = ""
        architecture = ""
        for line in block.splitlines():
            if line.startswith("Package: "):
                name = line[len("Package: ") :].strip()
            elif line.startswith("Version: "):
                version = line[len("Version: ") :].strip()
            elif line.startswith("Architecture: "):
                architecture = line[len("Architecture: ") :].strip()
        if name:
            packages.append(
                {"name": name, "version": version, "architecture": architecture}
            )

    packages.sort(key=lambda item: item["name"])
    return packages


def write_build_info(
    *,
    recipe: Recipe,
    iso_path: Path,
    digest: str,
    workdir: Path,
    bootappend: str,
    lb_args: list[str],
    source_date: str | None = None,
) -> Path:
    """何をどうやって作ったかを記録した JSON を ISO の隣に書く。

    レシピのハッシュも入れておくので、あとから「この ISO はどのレシピの
    どの版から作られたか」を辿れる。
    """
    recipe_digest = ""
    if recipe.path is not None and recipe.path.is_file():
        try:
            recipe_digest = sha256_bytes(recipe.path.read_bytes())
        except OSError:
            recipe_digest = ""

    packages = _installed_packages(workdir / "chroot")

    info = {
        "generator": GENERATED_BY,
        "project": PROJECT_NAME,
        "built_at": source_date or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recipe": {
            "path": str(recipe.path) if recipe.path else None,
            "sha256": recipe_digest,
        },
        "iso": {
            "file": iso_path.name,
            "size_bytes": iso_path.stat().st_size,
            "sha256": digest,
            "label": recipe.iso.resolved_label(),
            "application": recipe.iso.resolved_application(),
            "publisher": recipe.iso.resolved_publisher(),
            "preparer": recipe.iso.resolved_preparer(),
            "version": recipe.iso.version,
            "distribution": recipe.iso.distribution,
            "architecture": recipe.iso.architecture,
        },
        "desktop": recipe.desktop.environment,
        "bootappend": bootappend,
        "lb_config_args": lb_args,
        "requested_packages": list(recipe.packages.include),
        "excluded_packages": list(recipe.packages.exclude),
        "installed_package_count": len(packages),
        "installed_packages": packages,
        "builder_version": __version__,
    }

    target = iso_path.with_name(f"{iso_path.name}.build-info.json")
    target.write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


# --------------------------------------------------------------------------
# 署名
# --------------------------------------------------------------------------


def gpg_available() -> bool:
    return shutil.which("gpg") is not None


def sign_iso(iso_path: Path, key_id: str, echo: bool = False) -> Path:
    """ISO に GPG の分離署名を作る。

    `gpg --verify` で確かめられる形式 (ASCII armor の分離署名)。
    """
    if not gpg_available():
        raise BuildError(
            "gpg が見つかりません。",
            hint="sudo apt install gnupg で入れてください。",
        )

    signature = iso_path.with_name(f"{iso_path.name}.asc")
    command = [
        "gpg",
        "--armor",
        "--detach-sign",
        "--local-user",
        key_id,
        "--output",
        str(signature),
        str(iso_path),
    ]
    return_code = run_streaming(command, echo=echo)
    if return_code != 0 or not signature.is_file():
        raise BuildError(
            f"署名に失敗しました (終了コード {return_code})。",
            hint=f"鍵 {key_id} が秘密鍵として存在するか確認してください: gpg --list-secret-keys",
        )
    return signature


# --------------------------------------------------------------------------
# まとめ
# --------------------------------------------------------------------------


def produce(
    *,
    recipe: Recipe,
    iso_path: Path,
    workdir: Path,
    bootappend: str,
    lb_args: list[str],
    sign_key: str | None = None,
    checksums: bool = True,
    build_info: bool = True,
    echo: bool = False,
) -> ReleaseArtifacts:
    """配布に必要な成果物をまとめて作る。"""
    artifacts = ReleaseArtifacts(iso=iso_path)
    artifacts.sha256 = sha256_file(iso_path)

    if checksums:
        artifacts.checksum_files = write_checksums(iso_path, artifacts.sha256)

    if build_info:
        artifacts.build_info = write_build_info(
            recipe=recipe,
            iso_path=iso_path,
            digest=artifacts.sha256,
            workdir=workdir,
            bootappend=bootappend,
            lb_args=lb_args,
        )

    if sign_key:
        artifacts.signature = sign_iso(iso_path, sign_key, echo=echo)

    return artifacts
