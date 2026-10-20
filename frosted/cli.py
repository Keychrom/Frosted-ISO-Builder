"""コマンドラインインターフェース。

コマンドは「設定を作る (init/gen)」→「確認する (validate/show/doctor)」→
「実行する (build)」→「配る (verify)」→「あと始末 (clean/shell/test)」
という流れに沿って並べている。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import APP_NAME, PROJECT_NAME, __version__, release, ui
from .backend.livebuild import (
    build_bootappend,
    build_failsafe_append,
    build_lb_argv,
    generate,
)
from .catalog import DESKTOPS, PRESETS, apply_preset
from .errors import BuildError, FrostedError, PreflightError, RecipeError, UserAbort
from .i18n import t
from . import i18n
from .preflight import run as run_preflight
from .recipe import KNOWN_DISTRIBUTIONS, Recipe, RecipeProblems
from .runner import format_command, privileged, run_streaming, tail_file, which
from . import wizard

# --------------------------------------------------------------------------
# 引数の定義
# --------------------------------------------------------------------------

EPILOG = """\
例:
  # 対話でレシピを作って、そのままビルドする
  frosted init
  sudo frosted build mylinux.toml

  # 設定だけ生成して中身を確認する (root 不要)
  frosted gen mylinux.toml
  frosted show mylinux.toml

  # 環境に何が足りないか調べる
  frosted doctor

くわしくは README.md を見てください。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=f"{PROJECT_NAME} — Debian Live ISO をレシピ 1 枚から作るツール。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"{APP_NAME} {__version__}"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="色を付けない (ログに落とすとき)"
    )
    parser.add_argument(
        "--lang",
        choices=["ja", "en"],
        metavar="LANG",
        help="UI の言語。en か ja (既定: 環境変数 LANG / LC_ALL / FROSTED_LANG から自動判定)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="内部のコマンドも表示する"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="コマンド")

    # --- init ---------------------------------------------------------
    init_parser = subparsers.add_parser(
        "init", help="対話でレシピファイルを作る", description="対話でレシピファイルを作ります。"
    )
    init_parser.add_argument(
        "-o", "--output", metavar="FILE", help="書き出すレシピのパス (既定: <名前>.toml)"
    )
    init_parser.add_argument(
        "--preset", choices=sorted(PRESETS), help="用途プリセット (対話を一部省略します)"
    )
    init_parser.add_argument("--name", help="ISO の名前 (指定するとその質問を飛ばします)")
    init_parser.add_argument(
        "--distribution",
        choices=list(KNOWN_DISTRIBUTIONS),
        help="ベースにする Debian (testing/sid も選べます)",
    )
    init_parser.add_argument(
        "--arch", choices=["amd64", "i386", "arm64"], help="アーキテクチャ"
    )
    init_parser.add_argument(
        "--force", action="store_true", help="既存のファイルを上書きする"
    )
    init_parser.add_argument(
        "--yes", "-y", action="store_true", help="最後の確認を飛ばす"
    )

    # --- gen ----------------------------------------------------------
    gen_parser = subparsers.add_parser(
        "gen",
        help="live-build の設定だけ生成する (ビルドはしない)",
        description="レシピから live-build の設定ツリーを生成します。"
        "root 権限は不要で、生成物を目で確認したいときに便利です。",
    )
    gen_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    gen_parser.add_argument(
        "--quiet", "-q", action="store_true", help="生成したファイルの一覧を出さない"
    )

    # --- build --------------------------------------------------------
    build_parser_ = subparsers.add_parser(
        "build",
        help="レシピから ISO をビルドする",
        description="レシピから ISO をビルドします。数十分かかることがあります。",
    )
    build_parser_.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    build_parser_.add_argument(
        "--yes", "-y", action="store_true", help="開始前の確認を飛ばす"
    )
    build_parser_.add_argument(
        "--skip-preflight", action="store_true", help="環境の事前確認を飛ばす"
    )
    build_parser_.add_argument(
        "--no-network-check",
        action="store_true",
        help="ミラーへの到達確認をしない (プロキシ環境などで)",
    )
    build_parser_.add_argument(
        "--output", metavar="FILE", help="ISO のコピー先を上書きする"
    )
    build_parser_.add_argument(
        "--sign",
        metavar="KEYID",
        help="ISO に GPG の分離署名を作る。配布するなら指定する "
        "(例: --sign ABCD1234 や --sign you@example.com)",
    )
    build_parser_.add_argument(
        "--no-checksum",
        action="store_true",
        help="SHA256SUMS と build-info.json を作らない",
    )

    # --- validate -----------------------------------------------------
    validate_parser = subparsers.add_parser(
        "validate",
        help="レシピと環境を検証する (ビルドはしない)",
        description="レシピの内容とビルド環境を確認して、問題を一覧で出します。",
    )
    validate_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    validate_parser.add_argument(
        "--no-network", action="store_true", help="ネットワークの確認をしない"
    )
    validate_parser.add_argument(
        "--no-root", action="store_true", help="root 権限のチェックをしない"
    )

    # --- show ---------------------------------------------------------
    show_parser = subparsers.add_parser(
        "show",
        help="レシピの内容を表示する",
        description="レシピを読み込んだ結果と、実際に渡される設定を表示します。",
    )
    show_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    show_parser.add_argument(
        "--bootappend", action="store_true", help="ブートパラメータだけを出す"
    )
    show_parser.add_argument(
        "--lb-args", action="store_true", help="lb config に渡す引数だけを出す"
    )

    # --- doctor -------------------------------------------------------
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="ビルド環境を診断する",
        description="live-build 一式が揃っているか、空き容量は足りるかを確認します。",
    )
    doctor_parser.add_argument(
        "recipe", nargs="?", metavar="レシピ", help="レシピファイル (省略可)"
    )
    doctor_parser.add_argument(
        "--no-network", action="store_true", help="ネットワークの確認をしない"
    )

    # --- clean --------------------------------------------------------
    clean_parser = subparsers.add_parser(
        "clean",
        help="作業ディレクトリを掃除する",
        description="ビルドの成果物を消します。既定ではキャッシュを残すので、"
        "次回のビルドが速いままです。",
    )
    clean_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    clean_parser.add_argument(
        "--all", action="store_true", help="キャッシュも含めて全部消す"
    )

    # --- shell --------------------------------------------------------
    shell_parser = subparsers.add_parser(
        "shell",
        help="ビルド途中の chroot に入る",
        description="ビルド済みの chroot に入って中身を直接確認・修正します。"
        "レシピに書きづらい調整を試すときに使います。",
    )
    shell_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    shell_parser.add_argument(
        "--prepare",
        action="store_true",
        help="chroot が無ければ bootstrap と chroot を実行してから入る",
    )

    # --- test ---------------------------------------------------------
    test_parser = subparsers.add_parser(
        "test",
        help="QEMU で ISO を起動してみる",
        description="ビルドした ISO を QEMU で起動します。USB に焼く前に確認できます。",
    )
    test_parser.add_argument("recipe", metavar="レシピ", help="レシピファイル (TOML)")
    test_parser.add_argument("--iso", metavar="FILE", help="起動する ISO (既定: レシピの出力先)")
    test_parser.add_argument(
        "--memory", type=int, default=2048, metavar="MB", help="割り当てメモリ (既定: 2048)"
    )
    test_parser.add_argument("--uefi", action="store_true", help="UEFI で起動する")
    test_parser.add_argument(
        "--no-kvm", action="store_true", help="KVM を使わない (とても遅くなる)"
    )

    # --- verify -------------------------------------------------------
    verify_parser = subparsers.add_parser(
        "verify",
        help="配布された ISO を検証する",
        description="ISO のチェックサムと署名を検証します。"
        "配布物を受け取った側が実行する想定のコマンドです。",
    )
    verify_parser.add_argument(
        "iso", metavar="ISO", help="検証する ISO ファイル"
    )
    verify_parser.add_argument(
        "--sums",
        metavar="FILE",
        help="チェックサムファイル (既定: ISO と同じ場所の <ISO名>.sha256)",
    )
    verify_parser.add_argument(
        "--signature",
        metavar="FILE",
        help="署名ファイル (既定: ISO と同じ場所の <ISO名>.asc)",
    )

    # --- presets ------------------------------------------------------
    presets_parser = subparsers.add_parser(
        "presets", help="プリセットの一覧を出す", description="使えるプリセットの一覧です。"
    )
    presets_parser.add_argument(
        "name", nargs="?", help="名前を指定すると、そのプリセットの詳細を出します"
    )

    # --- gui ----------------------------------------------------------
    gui_parser = subparsers.add_parser(
        "gui",
        help="ブラウザでレシピを編集する",
        description="ローカル Web UI を起動します。127.0.0.1 にだけ待ち受けます。",
    )
    gui_parser.add_argument(
        "recipe",
        nargs="?",
        metavar="レシピ",
        help="開くレシピファイル (省略すると新規)",
    )
    gui_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        metavar="PORT",
        help="待ち受けポート (既定: 8765。0 で空きポートを自動選択)",
    )
    gui_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="ブラウザを自動で開かない",
    )

    return parser


# --------------------------------------------------------------------------
# ヘルパー
# --------------------------------------------------------------------------


def _load_recipe(path: str) -> Recipe:
    """レシピを読む。検証エラーは分かりやすく出して終了する。"""
    recipe = Recipe.load(path)
    if recipe.warnings:
        for issue in recipe.warnings:
            ui.warn(f"{issue.where}: {t(issue.message)}")
            if issue.hint:
                ui.hint(t(issue.hint))
        ui.out()
    return recipe


def _print_issues(prefix: str, problems: RecipeProblems) -> None:
    ui.err(f"{prefix}: {t('レシピに問題があります')}")
    for issue in problems.issues:
        # メッセージ本文を個別に訳す。行全体を渡すと、
        # 場所や記号が付いた状態では辞書を引けない。
        marker = ui.red(t("エラー")) if issue.is_error else ui.yellow(t("警告"))
        ui.hint(f"[{marker}] {issue.where}: {t(issue.message)}")
        if issue.hint:
            ui.hint(f"        {t(issue.hint)}")


def _report_preflight(report, *, exit_on_failure: bool = True) -> None:
    symbols = {
        "ok": ui.green("[OK]"),
        "warn": ui.yellow("[!]"),
        "fail": ui.red("[x]"),
        "skip": ui.dim("[-]"),
    }
    for check in report.checks:
        ui.out(
            f"  {symbols.get(check.status, '[?]')} {t(check.name)}: {t(check.detail)}"
        )
        if check.hint and check.status in ("fail", "warn"):
            ui.hint(t(check.hint))

    if report.failures and exit_on_failure:
        raise PreflightError(
            t(
                "ビルドできない問題が {count} 件あります。",
                count=len(report.failures),
            ),
            hint=t("上の [x] の項目を解消してから、もう一度実行してください。"),
        )


def _find_built_iso(workdir: Path, image_name: str) -> Path | None:
    """live-build が書き出した ISO を探す。

    ファイル名は live-build のバージョンや --image-name の解釈で変わりうるので、
    決め打ちせず実際に出来たものを探す。
    """
    candidates = [path for path in workdir.glob("*.iso") if path.is_file()]
    if not candidates:
        return None
    named = [path for path in candidates if path.name.startswith(image_name)]
    pool = named or candidates
    return max(pool, key=lambda path: path.stat().st_mtime)


def _cleanup_is_safe(workdir: Path, base_dir: Path) -> bool:
    """`clean --all` で消してよいディレクトリか。

    build.workdir の打ち間違いでレシピのあるディレクトリやその親、
    ホーム、ルートを丸ごと消す事故を防ぐ。
    """
    resolved = workdir.resolve()
    if resolved.parent == resolved:  # /
        return False
    if resolved == Path.home().resolve():
        return False
    base = base_dir.resolve()
    if resolved == base or resolved in base.parents:
        return False
    return True


def _display_width(text: str) -> int:
    """端末での表示幅。全角は 2、半角は 1 として数える。

    日本語と英語では文字の幅が違うので、単純な ljust だと桁がずれる。
    """
    import unicodedata

    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text
    )


def _kv(label: str, value: str, width: int = 12) -> None:
    """「項目名  値」の行を出す。項目名は訳してから幅を揃える。"""
    shown = t(label)
    ui.out(f"  {shown}{' ' * max(1, width - _display_width(shown))}{value}")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


# --------------------------------------------------------------------------
# コマンド
# --------------------------------------------------------------------------


def cmd_init(args) -> int:
    recipe = wizard.run(
        preset_key=args.preset,
        name=args.name,
        distribution=args.distribution,
        architecture=args.arch,
    )

    target = Path(args.output).expanduser() if args.output else wizard.suggest_path(recipe)
    recipe.path = target

    # ウィザードは Recipe を直接組み立てるので、保存前に通常の検証を通す。
    # ここを飛ばすと、ウィザードが選べるはずのない値や存在しない鍵パスを
    # そのまま保存し、次の `frosted build` で初めて失敗する。
    recipe = Recipe.from_dict(recipe.to_dict(), path=target)
    for issue in recipe.warnings:
        ui.warn(f"{issue.where}: {t(issue.message)}")
        if issue.hint:
            ui.hint(t(issue.hint))
    if recipe.warnings:
        ui.out()

    if target.exists() and not args.force:
        if not ui.ask_bool(
            f"{target} は既にあります。上書きしますか?", default=False
        ):
            ui.info("やめました。別の名前を指定してください (--output)。")
            return 1

    if not args.yes and not wizard.confirm(recipe):
        raise UserAbort("保存しませんでした。")

    saved = recipe.save(target)
    ui.ok(f"レシピを保存しました: {saved}")
    ui.out()
    ui.out("次はこれでビルドします:")
    ui.out(f"  sudo {APP_NAME} build {saved}")
    ui.out()
    ui.out("先に中身を確認したいときは:")
    ui.out(f"  {APP_NAME} gen {saved}")
    return 0


def cmd_gen(args) -> int:
    recipe = _load_recipe(args.recipe)
    ui.step("live-build の設定を生成します")

    result = generate(recipe)

    if not args.quiet:
        for path in result.created:
            ui.out(f"  {ui.dim(str(path))}")
    for warning in result.warnings:
        ui.warn(warning)

    ui.ok(f"{len(result.created)} 個のファイルを {result.workdir} に生成しました。")
    ui.out()
    ui.out(t("生成物を確認してください。とくに {path}",
            path=ui.bold(str(result.workdir / "auto" / "config"))))
    ui.out("次はこれでビルドします:")
    ui.out(f"  sudo {APP_NAME} build {args.recipe}")
    return 0


def cmd_build(args) -> int:
    recipe = _load_recipe(args.recipe)

    if not args.skip_preflight:
        ui.step("ビルド環境を確認します")
        report = run_preflight(
            recipe, require_root=True, check_network=not args.no_network_check
        )
        _report_preflight(report)

    if not args.yes:
        label_width = max(len(label) for label, _ in wizard.summarize(recipe))
        ui.out()
        for label, value in wizard.summarize(recipe):
            ui.out(f"  {label.ljust(label_width)}  {value}")
        ui.out()
        ui.warn("ビルドには数十分かかることがあります。")
        if not ui.ask_bool("始めますか?", default=True):
            raise UserAbort("やめました。")

    ui.step("設定を生成します")
    result = generate(recipe)
    for warning in result.warnings:
        ui.warn(warning)
    ui.ok(f"設定を {result.workdir} に生成しました。")

    log_path = result.workdir / "build.log"

    ui.step("lb config (設定の反映)")
    return_code = run_streaming(
        privileged(["lb", "config"]),
        cwd=result.workdir,
        log_path=log_path,
        echo=args.verbose,
    )
    if return_code != 0:
        raise BuildError(
            f"lb config が失敗しました (終了コード {return_code})",
            hint=f"ログ: {log_path}\n"
            "ヒント: live-build のバージョンによってオプション名が違うことがあります。"
            f" `{APP_NAME} doctor` で確認できます。",
        )

    ui.step("lb build (ISO を組み立てます)")
    ui.info("この段階が一番長いです。中断したいときは Ctrl-C。")
    return_code = run_streaming(
        privileged(["lb", "build"]),
        cwd=result.workdir,
        log_path=log_path,
        echo=args.verbose,
    )
    if return_code != 0:
        tail = tail_file(log_path, 40)
        ui.out()
        ui.err(t("lb build が失敗しました (終了コード {code})", code=return_code))
        if tail:
            ui.out()
            ui.out(ui.dim("--- ログの末尾 ---"))
            ui.out(tail)
            ui.out(ui.dim("--- ここまで ---"))
        raise BuildError(
            "ISO を組み立てられませんでした。",
            hint=f"ログ全体: {log_path}",
        )

    ui.step("ISO を取り出します")
    built = _find_built_iso(result.workdir, result.image_name)
    if built is None:
        raise BuildError(
            "lb build は成功しましたが ISO が見つかりません。",
            hint=f"{result.workdir} の中を確認してください。",
        )

    destination = (
        Path(args.output).expanduser().resolve()
        if args.output
        else recipe.output_path()
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, destination)

    ui.ok("ビルドできました。")
    ui.out()
    ui.out(f"  ISO      {ui.bold(str(destination))}")
    _kv("大きさ", _human_size(destination.stat().st_size))
    _kv("ログ", str(log_path))

    # 配布に必要な成果物を ISO の隣に作る
    ui.step("配布用の成果物を作ります")
    try:
        artifacts = release.produce(
            recipe=recipe,
            iso_path=destination,
            workdir=result.workdir,
            bootappend=result.bootappend,
            lb_args=result.lb_args,
            sign_key=args.sign,
            checksums=not args.no_checksum,
            build_info=not args.no_checksum,
            echo=args.verbose,
        )
    except BuildError as error:
        # ISO 自体はできているので、成果物が作れなくても失敗にはしない
        ui.warn(error.message)
        if error.hint:
            ui.hint(error.hint)
        artifacts = None

    if artifacts is not None:
        ui.out()
        ui.out(f"  SHA-256  {artifacts.sha256}")
        for path in artifacts.checksum_files:
            ui.out(f"  {t('検証用').ljust(9)} {path.name}")
        if artifacts.build_info:
            ui.out(f"  {t('ビルド情報').ljust(9)} {artifacts.build_info.name}")
        if artifacts.signature:
            ui.out(f"  {t('署名').ljust(9)} {artifacts.signature.name}")

    ui.out()
    ui.out("次はこれで起動を確認できます:")
    ui.out(f"  {APP_NAME} test {args.recipe}")
    ui.out()
    ui.out("USB に焼くときは:")
    ui.out(f"  sudo dd if={destination} of=/dev/sdX bs=4M status=progress oflag=sync")
    ui.out(ui.dim("  ※ /dev/sdX は必ず自分の環境に合わせて確認してください。間違えるとデータが消えます。"))

    if artifacts is not None and artifacts.checksum_files:
        ui.out()
        ui.out("配布するときは、ISO と一緒に次のファイルも渡してください:")
        names = [path.name for path in artifacts.checksum_files]
        if artifacts.build_info:
            names.append(artifacts.build_info.name)
        if artifacts.signature:
            names.append(artifacts.signature.name)
        for name in names:
            ui.out(f"  {name}")
        ui.out()
        ui.out("受け取った側はこうやって検証できます:")
        ui.out(f"  sha256sum -c SHA256SUMS")
        if artifacts.signature:
            ui.out(f"  gpg --verify {artifacts.signature.name} {destination.name}")
    return 0


def cmd_validate(args) -> int:
    recipe = Recipe.load(args.recipe)
    ui.step(t("レシピを確認します: {path}", path=args.recipe))

    if recipe.warnings:
        for issue in recipe.warnings:
            ui.warn(f"{issue.where}: {t(issue.message)}")
            if issue.hint:
                ui.hint(t(issue.hint))
    else:
        ui.ok("レシピの内容に問題はありません。")

    ui.step("ビルド環境を確認します")
    report = run_preflight(
        recipe, require_root=not args.no_root, check_network=not args.no_network
    )
    _report_preflight(report, exit_on_failure=False)

    if report.failures:
        ui.out()
        ui.err(t("ビルドできない問題が {count} 件あります。", count=len(report.failures)))
        return 1
    ui.ok("この環境でビルドできます。")
    return 0


def cmd_show(args) -> int:
    recipe = _load_recipe(args.recipe)

    if args.bootappend:
        ui.out(build_bootappend(recipe))
        return 0

    if args.lb_args:
        argv, warnings = build_lb_argv(recipe)
        for warning in warnings:
            ui.warn(warning)
        # そのままコピペして実行できる形で出す
        ui.out(format_command(argv))
        return 0

    ui.header(f"{recipe.iso.name} {recipe.iso.version}")
    label_width = max(len(label) for label, _ in wizard.summarize(recipe))
    for label, value in wizard.summarize(recipe):
        ui.out(f"  {label.ljust(label_width)}  {value}")

    ui.step("ブートパラメータ")
    ui.out(f"  {build_bootappend(recipe)}")
    ui.out()
    ui.out(ui.dim("  failsafe:"))
    ui.out(f"  {build_failsafe_append(recipe)}")
    if recipe.boot.install_append:
        ui.out(ui.dim(t("  インストール先: {params}", params=recipe.boot.install_append)))

    ui.step("lb config に渡す引数")
    argv, warnings = build_lb_argv(recipe)
    for warning in warnings:
        ui.warn(warning)
    for item in argv:
        ui.out(f"  {item}")

    if recipe.packages.include or recipe.packages.exclude or recipe.packages.local:
        ui.step("パッケージ")
        if recipe.packages.include:
            ui.out(t("  追加: {packages}", packages=" ".join(recipe.packages.include)))
        if recipe.packages.exclude:
            ui.out(t("  除外: {packages}", packages=" ".join(recipe.packages.exclude)))
        for deb in recipe.packages.local:
            ui.out(t("  同梱: {path}", path=deb))

    if recipe.files.copy or recipe.files.write:
        ui.step("ファイル")
        for entry in recipe.files.copy:
            ui.out(t("  コピー  {source} -> {target}", source=entry.source, target=entry.target))
        for entry in recipe.files.write:
            ui.out(t("  書き込み {path}", path=entry.path))

    if recipe.desktop.wallpaper:
        ui.step("デスクトップ")
        ui.out(t("  壁紙 {path}", path=recipe.desktop.wallpaper))

    if recipe.build.extra_repositories or recipe.build.repository_keys:
        ui.step("リポジトリ")
        for line in recipe.build.extra_repositories:
            ui.out(t("  追加: {line}", line=line))
        for key in recipe.build.repository_keys:
            ui.out(t("  鍵: {path}", path=key))
        if recipe.apt.preferences.strip():
            ui.out(t("  APT のピン留め: 設定あり"))

    if recipe.binary.swap_file_path:
        ui.step("スワップファイル")
        size = recipe.binary.swap_file_size or 512
        ui.out(
            t(
                "  {path} ({size} MB)",
                path=recipe.binary.swap_file_path,
                size=size,
            )
        )

    if recipe.scripts.setup or recipe.scripts.firstboot:
        ui.step("スクリプト")
        for script in recipe.scripts.setup:
            ui.out(t("  ビルド時   {path}", path=script))
        for script in recipe.scripts.firstboot:
            ui.out(t("  初回起動時 {path}", path=script))
    return 0


def cmd_doctor(args) -> int:
    ui.step("ビルド環境を診断します")

    if args.recipe:
        recipe = _load_recipe(args.recipe)
    else:
        # レシピが無くても環境だけ見られるように、最小構成のレシピで代用する
        recipe = Recipe()
        recipe.iso.name = "doctor"
        ui.info("レシピが指定されていないので、既定の設定で環境だけ確認します。")

    report = run_preflight(
        recipe, require_root=False, check_network=not args.no_network
    )
    _report_preflight(report, exit_on_failure=False)

    ui.out()
    if report.failures:
        missing = [check for check in report.failures if check.name == "必須ツール"]
        if missing:
            ui.out("必要なものをまとめて入れるには:")
            ui.out("  sudo apt install live-build debootstrap xorriso squashfs-tools \\")
            ui.out("      cpio rsync uuid-runtime mtools dosfstools syslinux-common \\")
            ui.out("      isolinux grub-efi-amd64-bin grub-pc-bin")
            ui.out()
        ui.err("この環境ではビルドできません。")
        return 1

    ui.ok("ビルドできる環境です。")
    if report.warnings:
        ui.info(t("警告が {count} 件ありますが、ビルドはできます。", count=len(report.warnings)))
    return 0


def cmd_clean(args) -> int:
    recipe = _load_recipe(args.recipe)
    workdir = recipe.workdir()

    if not workdir.exists():
        ui.info(t("作業ディレクトリがありません: {path}", path=workdir))
        return 0

    if args.all:
        if not _cleanup_is_safe(workdir, recipe.base_dir):
            raise BuildError(
                f"この作業ディレクトリは削除できません: {workdir}",
                hint="build.workdir がレシピのあるディレクトリやその親、"
                "ホーム、ルートを指していないか確認してください。",
            )
        if not ui.ask_bool(
            f"{workdir} を中身ごと削除します。よろしいですか?", default=False
        ):
            raise UserAbort("やめました。")
        shutil.rmtree(workdir, ignore_errors=True)
        ui.ok(f"削除しました: {workdir}")
        return 0

    ui.step("ビルドの成果物を消します (キャッシュは残します)")
    return_code = run_streaming(
        privileged(["lb", "clean", "noauto"]),
        cwd=workdir,
        log_path=workdir / "clean.log",
        echo=args.verbose,
    )
    if return_code != 0:
        ui.warn(
            "lb clean が失敗しました。--all で作業ディレクトリごと消すこともできます。"
        )
        return return_code
    ui.ok("掃除しました。キャッシュは残っているので次のビルドは速いです。")
    return 0


def cmd_shell(args) -> int:
    recipe = _load_recipe(args.recipe)
    workdir = recipe.workdir()
    chroot_dir = workdir / "chroot"

    if not chroot_dir.is_dir():
        if not args.prepare:
            raise BuildError(
                f"chroot がまだありません: {chroot_dir}",
                hint=f"`{APP_NAME} build` を先に実行するか、--prepare を付けてください。",
            )
        ui.info("chroot が無いので先に用意します (少し時間がかかります)。")
        for stage in ("bootstrap", "chroot"):
            code = run_streaming(
                privileged(["lb", stage, "noauto"]),
                cwd=workdir,
                log_path=workdir / f"{stage}.log",
                echo=args.verbose,
            )
            if code != 0:
                raise BuildError(
                    f"lb {stage} が失敗しました。",
                    hint=f"ログ: {workdir / (stage + '.log')}",
                )

    return _enter_chroot(chroot_dir)


def _enter_chroot(chroot_dir: Path) -> int:
    """chroot に入る。必要なものだけ bind マウントし、必ず外してから戻る。"""
    mounts: list[tuple[str, Path, list[str]]] = [
        ("/dev", chroot_dir / "dev", ["--bind"]),
        ("/dev/pts", chroot_dir / "dev" / "pts", ["--bind"]),
        ("/proc", chroot_dir / "proc", ["-t", "proc", "proc"]),
        ("/sys", chroot_dir / "sys", ["--bind"]),
    ]

    mounted: list[Path] = []
    for source, target, options in mounts:
        target.mkdir(parents=True, exist_ok=True)
        code = run_streaming(
            privileged(["mount", *options, source, str(target)]),
            echo=False,
            quiet=True,
        )
        if code == 0:
            mounted.append(target)

    try:
        ui.info("chroot に入ります。抜けるときは exit と入力してください。")
        return run_streaming(privileged(["chroot", str(chroot_dir), "/bin/bash", "-i"]))
    finally:
        # chroot から抜けたら必ず外す。外し忘れると次のビルドが汚い状態で走る。
        for target in reversed(mounted):
            run_streaming(
                privileged(["umount", str(target)]), echo=False, quiet=True
            )


def cmd_test(args) -> int:
    recipe = _load_recipe(args.recipe)

    iso = (
        Path(args.iso).expanduser().resolve()
        if args.iso
        else recipe.output_path()
    )
    if not iso.is_file():
        raise BuildError(
            f"ISO が見つかりません: {iso}",
            hint=f"先に `{APP_NAME} build {args.recipe}` を実行してください。",
        )

    if recipe.iso.architecture == "arm64":
        raise BuildError(
            "frosted test は今のところ amd64/i386 用です。",
            hint="arm64 の ISO は実機か、qemu-system-aarch64 と AAVMF で起動してください。",
        )

    if which("qemu-system-x86_64") is None:
        raise BuildError(
            "QEMU がインストールされていません。",
            hint="sudo apt install qemu-system-x86",
        )

    command = ["qemu-system-x86_64", "-m", str(args.memory), "-cdrom", str(iso)]

    if not args.no_kvm and Path("/dev/kvm").exists():
        command.append("-enable-kvm")
    elif not args.no_kvm:
        ui.warn("/dev/kvm が無いのでエミュレーションで起動します。とても遅くなります。")

    if args.uefi:
        firmware = _find_ovmf()
        if firmware is None:
            raise BuildError(
                "UEFI 用のファームウェア (OVMF) が見つかりません。",
                hint="sudo apt install ovmf",
            )
        command += [
            "-drive",
            f"if=pflash,format=raw,readonly=on,file={firmware}",
        ]
    else:
        command += ["-boot", "d"]

    ui.info(t("起動します: {name}", name=iso.name))
    ui.hint("終了するときは QEMU のウィンドウを閉じるか、Ctrl-A のあと X を押します。")
    return run_streaming(command)


def _find_ovmf() -> Path | None:
    candidates = (
        "/usr/share/OVMF/OVMF_CODE.fd",
        "/usr/share/ovmf/OVMF.fd",
        "/usr/share/OVMF/OVMF_CODE_4M.fd",
        "/usr/share/qemu/OVMF.fd",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return Path(candidate)
    return None


def cmd_presets(args) -> int:
    if args.name:
        preset = PRESETS.get(args.name)
        if preset is None:
            ui.err(t("知らないプリセットです: {name}", name=args.name))
            ui.out(t("選べるもの: {items}", items=", ".join(sorted(PRESETS))))
            return 1
        ui.header(t("{label} ({key})", label=t(preset.label), key=preset.key))
        ui.out(f"  {t(preset.description)}")
        ui.out()
        ui.out("  " + t("このプリセットに含まれるパッケージ:"))
        recipe = Recipe()
        recipe.iso.name = "preview"
        apply_preset(recipe, preset.key)
        ui.out(t("    デスクトップ: {value}", value=recipe.desktop.environment))
        ui.out(t("    自動ログイン: {value}",
                  value=t("あり") if recipe.user.autologin else t("なし")))
        ui.out(t("    sudo:         {value}",
                  value=t("あり") if recipe.user.sudo else t("なし")))
        ui.out(t("    SSH:          {value}",
                  value=t("有効") if recipe.ssh.enable_server else t("無効")))
        if recipe.packages.include:
            ui.out()
            ui.out(t("    追加パッケージ:"))
            for name in recipe.packages.include:
                ui.out(f"      {name}")
        return 0

    ui.header("使えるプリセット")
    for key, preset in PRESETS.items():
        ui.out(f"  {ui.bold(key.ljust(10))} {t(preset.label)}")
        ui.out(f"  {' ' * 10} {ui.dim(t(preset.description))}")
    ui.out()
    ui.out(t("使い方: {command}", command=f"{APP_NAME} init --preset <name>"))
    ui.out(t("詳細:   {command}", command=f"{APP_NAME} presets <name>"))
    ui.out()
    ui.out(t("デスクトップ環境の選択肢:"))
    for key, profile in DESKTOPS.items():
        ui.out(f"  {ui.bold(key.ljust(10))} {t(profile.description)}")
    return 0


def cmd_gui(args) -> int:
    """ローカル Web UI を起動する。"""
    # GUI は http.server だけを使うので、CLI の起動を重くしないよう
    # ここで遅延インポートする。
    from .gui.server import serve

    recipe = Path(args.recipe).expanduser() if args.recipe else None
    try:
        serve(
            recipe,
            port=args.port,
            open_browser=not args.no_browser,
        )
    except OSError as exc:
        raise BuildError(
            t("GUI を起動できませんでした: {error}", error=exc),
            hint=t("--port で別のポートを指定してください。"),
        ) from exc
    return 0


def cmd_verify(args) -> int:
    """配布された ISO を検証する。

    受け取った側の人が最初にやることなので、結果を明快に出す。
    チェックサムが合わなければ署名も見る意味がないので、そこでは止める。
    """
    iso = Path(args.iso).expanduser().resolve()
    if not iso.is_file():
        raise BuildError(
            f"ISO が見つかりません: {iso}",
            hint="パスを確認してください。",
        )

    ui.step(t("検証します: {name}", name=iso.name))
    _kv("大きさ", _human_size(iso.stat().st_size))

    failed = False
    verified = False

    # --- チェックサム ---
    sums_path = (
        Path(args.sums).expanduser().resolve()
        if args.sums
        else iso.with_name(f"{iso.name}.sha256")
    )
    if sums_path.is_file():
        expected = _expected_digest(sums_path, iso.name)
        if expected is None:
            ui.warn(
                t(
                    "チェックサムファイルにこの ISO の行がありません: {name}",
                    name=sums_path.name,
                )
            )
        else:
            actual = release.sha256_file(iso)
            if actual == expected:
                ui.ok(f"チェックサムが一致しました ({actual})")
                verified = True
            else:
                ui.err("チェックサムが一致しません。ファイルが壊れているか改ざんされています。")
                ui.hint(f"  期待値 {expected}")
                ui.hint(f"  実際   {actual}")
                failed = True
    else:
        ui.warn(t("チェックサムファイルがありません: {name}", name=sums_path.name))
        ui.hint("ISO だけを渡されている場合は検証できません。")

    # --- 署名 ---
    signature = (
        Path(args.signature).expanduser().resolve()
        if args.signature
        else iso.with_name(f"{iso.name}.asc")
    )
    if signature.is_file():
        if not release.gpg_available():
            ui.warn("署名はありますが gpg が無いので検証できません。")
            ui.hint("sudo apt install gnupg で入れてください。")
        else:
            code = run_streaming(
                ["gpg", "--verify", str(signature), str(iso)],
                echo=args.verbose,
                quiet=not args.verbose,
            )
            if code == 0:
                ui.ok("署名を検証できました。")
                verified = True
            else:
                ui.err("署名の検証に失敗しました。")
                ui.hint("配布元の公開鍵をインポートしてあるか確認してください。")
                failed = True
    else:
        ui.info("署名ファイルはありません。")

    # --- ビルド情報 ---
    info_path = iso.with_name(f"{iso.name}.build-info.json")
    if info_path.is_file():
        try:
            import json

            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        # build-info.json は配布物と一緒に運ばれる外部データなので、
        # 中身が期待した辞書でなくても落ちないようにする。
        if isinstance(info, dict) and info:
            ui.out()
            ui.out("  ビルド情報:")
            iso_info = info.get("iso")
            if not isinstance(iso_info, dict):
                iso_info = {}
            for label, key in (
                ("作成元", "publisher"),
                ("識別子", "application"),
                ("バージョン", "version"),
                ("ベース", "distribution"),
                ("アーキテクチャ", "architecture"),
                ("ビルド日時", "built_at"),
            ):
                value = info.get(key) if key == "built_at" else iso_info.get(key)
                if value:
                    ui.out(f"    {label.ljust(14)} {value}")
            count = info.get("installed_package_count")
            if isinstance(count, int) and count:
                ui.out(f"    {'パッケージ数'.ljust(14)} {count}")

    ui.out()
    if failed:
        ui.err("検証に失敗しました。")
        return 1
    if not verified:
        # ファイルが存在するだけでは成功ではない。該当行の無いチェックサム
        # ファイルや、gpg が無くて確認できなかった署名だけの状態で
        # 「検証できました」と言ってはいけない。
        ui.warn("検証できるものがありませんでした。")
        return 1
    ui.ok("検証できました。")
    return 0


def _expected_digest(sums_path: Path, iso_name: str) -> str | None:
    """チェックサムファイルからこの ISO の行を探す。

    `<ISO名>.sha256` でも `SHA256SUMS` でも同じ形式なので、同じ読み方で済む。
    """
    try:
        text = sums_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] and parts[-1].lstrip("*") == iso_name:
            return parts[0].lower()
    # ファイル名が一致する行が無ければ、1 行だけならそれを使う
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) == 1:
        parts = lines[0].split()
        if parts:
            return parts[0].lower()
    return None


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

COMMANDS = {
    "init": cmd_init,
    "gen": cmd_gen,
    "build": cmd_build,
    "validate": cmd_validate,
    "show": cmd_show,
    "doctor": cmd_doctor,
    "clean": cmd_clean,
    "shell": cmd_shell,
    "test": cmd_test,
    "verify": cmd_verify,
    "presets": cmd_presets,
    "gui": cmd_gui,
}


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    """サブコマンド側でも `--lang` などを書けるようにする。

    argparse ではグローバルオプションはサブコマンドの前に置く必要があるが、
    `frosted init --lang en` と書きたくなるのが自然なので同じものを足す。
    default=SUPPRESS にしてあるので、指定が無ければグローバル側の値を
    上書きしない。
    """
    for action in getattr(parser, "_actions", []):
        choices = getattr(action, "choices", None)
        if not isinstance(choices, dict):
            continue
        for sub in choices.values():
            if not isinstance(sub, argparse.ArgumentParser):
                continue
            sub.add_argument(
                "--lang",
                choices=["ja", "en"],
                default=argparse.SUPPRESS,
                metavar="LANG",
                help="UI の言語。en か ja",
            )
            sub.add_argument(
                "--no-color",
                action="store_true",
                default=argparse.SUPPRESS,
                help="色を付けない (ログに落とすとき)",
            )
            sub.add_argument(
                "--verbose",
                "-v",
                action="store_true",
                default=argparse.SUPPRESS,
                help="内部のコマンドも表示する",
            )
            _add_common_options(sub)

def _translate_parser(parser: argparse.ArgumentParser) -> None:
    """パーサが抱えている説明文をまとめて訳す。

    argparse は `help=` や `description=` の文字列を組み立て時に取り込んで
    しまうので、後から辿って差し替える。こうしないと 60 か所ある
    `help=` の一つ一つに `t()` を書くことになり、コマンドを足すたびに
    書き忘れが起きる。

    サブコマンドの説明は `_choices_actions` という別の場所に入っているので、
    そちらも見る必要がある。argparse の内部に触るのは気持ち悪いが、
    万一属性が無くなっても静かに諦めるだけで、表示が日本語に戻る以外の
    害はない。
    """
    if parser.description:
        parser.description = t(parser.description)
    if parser.epilog:
        parser.epilog = t(parser.epilog)

    for action in getattr(parser, "_actions", []):
        if action.help:
            action.help = t(action.help)
        if action.metavar:
            action.metavar = t(action.metavar)

        # サブコマンド一覧の 1 行説明
        for pseudo in getattr(action, "_choices_actions", []) or []:
            if pseudo.help:
                pseudo.help = t(pseudo.help)
            if pseudo.metavar:
                pseudo.metavar = t(pseudo.metavar)

        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            for subparser in choices.values():
                if isinstance(subparser, argparse.ArgumentParser):
                    _translate_parser(subparser)


def _language_from_argv(argv: list[str]) -> str | None:
    """`--lang` を argv から先に拾う。

    `--help` と `--version` は argparse が parse_args の中で処理して
    しまうので、そこより前に言語を決めておかないと英語で出せない。
    """
    for index, item in enumerate(argv):
        if item == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--lang="):
            return item.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    # argparse の出力 (--help など) より先に言語を確定させる
    try:
        i18n.set_language(_language_from_argv(raw_argv))
    except ValueError:
        # 値が変なときは argparse に判定させる (choices で弾かれる)
        i18n.set_language(None)

    parser = build_parser()
    _add_common_options(parser)
    _translate_parser(parser)
    args = parser.parse_args(raw_argv)

    ui.init_output()
    ui.init_color(force=False if args.no_color else None)

    if not args.command:
        parser.print_help()
        return 0

    if sys.version_info < (3, 11):
        ui.err(
            t(
                "Python 3.11 以上が必要です (今は {version})。",
                version=f"{sys.version_info.major}.{sys.version_info.minor}",
            )
        )
        ui.hint("TOML を読むために標準ライブラリの tomllib を使っています。")
        return 1

    try:
        return COMMANDS[args.command](args)
    except RecipeProblems as problems:
        _print_issues("レシピを読み込めません", problems)
        return 1
    except UserAbort as abort:
        ui.out()
        ui.info(abort.message)
        return 130
    except FrostedError as error:
        ui.out()
        ui.err(error.message)
        if error.hint:
            ui.hint(error.hint)
        return 1
    except OSError as error:
        # 書き込み権限が無い、ディスクが一杯など。トレースバックを出すより
        # 「どこで失敗したか」を 1 行で伝えたほうが利用者は助かる。
        ui.out()
        ui.err(t("ファイル操作に失敗しました: {error}", error=error))
        return 1
    except KeyboardInterrupt:
        ui.out()
        ui.info("中断しました。")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
