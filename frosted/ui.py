"""ターミナル出力と対話入力のヘルパー。

文字装飾記号 (罫線や記号) はあえて ASCII の `[OK]` / `[!]` / `[x]` にしている。
ビルドは SSH 越しの最小 Debian で走らせることが多く、フォントやロケールが
貧弱でも確実に読めることを優先した。

**ここを通した文字列は自動で翻訳される。** 呼び出し側で `t()` を書く必要は
ない (書いても害はない)。文言を訳す場所を 1 か所に決めておかないと、どこで
訳されたか分からなくなるため、出力の出口をここに集約している。
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Sequence

from .errors import UserAbort
from .i18n import t

# --------------------------------------------------------------------------
# 色
# --------------------------------------------------------------------------

_USE_COLOR = False


def init_output() -> None:
    """標準出力をライン バッファリングにする。

    発見した問題は stderr に、通常の出力は stdout に出す。パイプや
    リダイレクト経由だと stdout がブロック単位で溜め込まれ、後から出した
    stderr のほうが先に表示されてしまう。出力順が入れ替わると、どの
    メッセージがどの確認結果に対応するのか分からなくなるので、ここで揃える。
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(line_buffering=True)
    except (ValueError, OSError):
        # 既に閉じられているなど。出力自体は続けられるので致命傷にしない。
        pass


def init_color(force: bool | None = None) -> None:
    """色を使うかどうかを決める。

    force が True/False ならそれに従う。None なら TTY かつ NO_COLOR 未設定の
    ときだけ色を使う (パイプやリダイレクト時にエスケープシーケンスを
    混入させないため)。
    """
    global _USE_COLOR
    if force is not None:
        _USE_COLOR = force
        return
    _USE_COLOR = bool(
        sys.stdout.isatty()
        and os.environ.get("TERM", "") not in ("", "dumb")
        and "NO_COLOR" not in os.environ
    )


def _wrap(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _wrap("1", text)


def dim(text: str) -> str:
    return _wrap("2", text)


def red(text: str) -> str:
    return _wrap("31", text)


def green(text: str) -> str:
    return _wrap("32", text)


def yellow(text: str) -> str:
    return _wrap("33", text)


def blue(text: str) -> str:
    return _wrap("34", text)


def cyan(text: str) -> str:
    return _wrap("36", text)


# --------------------------------------------------------------------------
# 出力
# --------------------------------------------------------------------------


def _emit(text: str = "", stream=None) -> None:
    """1 行出す。毎回 flush するのが大事。

    エラーは stderr に出すので、stdout がバッファされていると
    パイプやリダイレクト経由で出力順が入れ替わって読めなくなる。

    stream の既定値は呼び出し時に解決する。既定引数にすると
    モジュール読み込み時の sys.stdout に固定されてしまい、
    出力先を差し替えられなくなるため。
    """
    print(text, file=stream if stream is not None else sys.stdout, flush=True)


def out(message: str = "") -> None:
    _emit(t(message))


def ok(message: str) -> None:
    _emit(f"{green('[OK]')} {t(message)}")


def warn(message: str) -> None:
    _emit(f"{yellow('[!]')} {t(message)}")


def err(message: str) -> None:
    _emit(f"{red('[x]')} {t(message)}", stream=sys.stderr)


def info(message: str) -> None:
    _emit(f"{blue('[i]')} {t(message)}")


def hint(message: str) -> None:
    """補足情報。エラーの対処法などをぶら下げるのに使う。"""
    _emit(f"     {dim(t(message))}")


def step(message: str) -> None:
    """大きな処理の区切り。"""
    _emit(f"\n{cyan('==>')} {bold(t(message))}")


def header(title: str) -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, 72)
    translated = t(title)
    _emit()
    _emit(bold(translated))
    _emit(dim("-" * min(width, max(len(translated), 8))))


def terminal_width(default: int = 80) -> int:
    return shutil.get_terminal_size((default, 24)).columns


# --------------------------------------------------------------------------
# 入力
# --------------------------------------------------------------------------

#: 空入力を「デフォルト採用」とみなすかどうかを呼び出し側が制御できるようにする。
Validator = Callable[[str], "str | None"]


def _prompt_text(label: str, default: str | None) -> str:
    if default:
        return f"{t(label)} {dim('[' + default + ']')}: "
    return f"{t(label)}: "


def _read_line(label: str, default: str | None) -> str:
    try:
        raw = input(_prompt_text(label, default))
    except EOFError as exc:  # パイプ入力が尽きた
        raise UserAbort(t("入力が終了しました。")) from exc
    except KeyboardInterrupt as exc:
        raise UserAbort() from exc
    return raw.strip()


def ask(
    label: str,
    default: str | None = None,
    validate: Validator | None = None,
    allow_empty: bool = False,
) -> str:
    """1行入力を求める。

    default があれば空 Enter でそれを採用する。validate が文字列を返したら
    それをエラーメッセージとして表示し、もう一度聞き直す。
    """
    while True:
        raw = _read_line(label, default)
        if not raw:
            if default is not None:
                return default
            if allow_empty:
                return ""
            warn("入力してください。")
            continue
        if validate is not None:
            problem = validate(raw)
            if problem:
                warn(problem)
                continue
        return raw


def ask_bool(label: str, default: bool = False) -> bool:
    """はい/いいえ。Enter で default。"""
    suffix = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"{t(label)} {dim('[' + suffix + ']')}: ").strip().lower()
        except EOFError as exc:
            raise UserAbort(t("入力が終了しました。")) from exc
        except KeyboardInterrupt as exc:
            raise UserAbort() from exc
        if not raw:
            return default
        if raw in ("y", "yes", "はい", "h"):
            return True
        if raw in ("n", "no", "いいえ", "i"):
            return False
        warn("y か n で答えてください。")


def ask_choice(
    label: str,
    options: Sequence[tuple[str, str]],
    default_index: int = 0,
    descriptions: bool = True,
) -> str:
    """番号で選ばせる。

    options は (値, 説明) の並び。戻り値は選ばれた「値」のほう。
    説明文も翻訳されるので、カタログの文言をそのまま渡してよい。
    """
    shown = [(value, t(text)) for value, text in options]
    print()
    print(bold(t(label)))
    value_width = max(len(value) for value, _ in shown)
    for index, (value, text) in enumerate(shown, start=1):
        marker = cyan(">") if index - 1 == default_index else " "
        line = f" {marker} {index}) {value.ljust(value_width)}"
        if descriptions and text:
            line += f"  {dim(text)}"
        print(line)
    print()
    while True:
        try:
            raw = input(
                f"{t(label)} {dim('[' + str(default_index + 1) + ']')}: "
            ).strip()
        except EOFError as exc:
            raise UserAbort(t("入力が終了しました。")) from exc
        except KeyboardInterrupt as exc:
            raise UserAbort() from exc
        if not raw:
            return options[default_index][0]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        warn(t("1 から {count} の番号で答えてください。", count=len(options)))


def ask_password(label: str) -> str:
    """パスワードを入力させる。

    端末から直接入力されているときは画面に出さない。パイプや
    リダイレクト経由 (自動化) のときは getpass が使えないので、
    普通の 1 行入力に落とす。
    """
    if not sys.stdin.isatty():
        return ask(label, default="", allow_empty=True)

    import getpass

    def _read(prompt: str) -> str:
        try:
            return getpass.getpass(prompt)
        except EOFError as exc:
            raise UserAbort(t("入力が終了しました。")) from exc
        except KeyboardInterrupt as exc:
            raise UserAbort() from exc

    while True:
        first = _read(f"{t(label)} {t(' (入力は画面に出ません): ')}")
        if not first:
            return ""
        second = _read(t("確認のためもう一度: "))
        if first == second:
            return first
        warn("一致しません。もう一度入力してください。")


def ask_list(label: str, default: Sequence[str] = ()) -> list[str]:
    """空白/カンマ区切りのリスト入力。空 Enter で default。"""
    default_text = " ".join(default)
    raw = ask(label, default=default_text or None, allow_empty=not default)
    return split_list(raw)


def split_list(text: str) -> list[str]:
    """空白またはカンマ区切りの文字列をリストにする。重複は落として順序は保つ。"""
    parts = text.replace(",", " ").split()
    seen: set[str] = set()
    result: list[str] = []
    for item in parts:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def confirm_or_abort(question: str, default: bool = True) -> None:
    """実行前に最終確認する。拒否されたら UserAbort を投げる。"""
    if not ask_bool(question, default=default):
        raise UserAbort()
