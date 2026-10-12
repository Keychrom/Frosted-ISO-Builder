"""UI の文言の多言語化。

設計は gettext と同じで、**日本語の原文をそのままキーにしている**。
こうするとソースを読んだときに実際に表示される文がそのまま見えるので、
キーと本文を往復して確認しなくて済む。

    t("保存しました")                       # そのまま
    t("コマンドが見つかりません: {name}", name="lb")

翻訳が無い場合は原文 (日本語) をそのまま返す。表示が壊れるよりましで、
漏れは `tests/test_i18n.py` が検出する。

## テンプレート文の扱い

`f"使えない名前です: {name!r}"` のように値が埋め込まれた文は、組み立てた
後では辞書を引けない。かといって検証コードの隅々に `t()` を撒くと、
何を言いたいのか読み取りにくくなる。

そこで、値が入る文は 2 段構えで訳す。

1. `PREFIXES` — `「前置き: 値」` の形の文の前置き部分だけを訳す。
   検証メッセージの大半はこの形なので、これだけでほとんど済む。
2. `PATTERNS` — それ以外の型にはまらない文を正規表現で訳す。

どちらも値の部分には手を触れないので、`'My Linux'` のような引用符付きの
値や、`lb config --help` のようなコマンド例がそのまま残る。
"""

from __future__ import annotations

import os
import re

from .i18n_en import EN, PATTERNS, PREFIXES

#: 対応している言語
SUPPORTED = ("en", "ja")

#: 判別できなかったときに使う言語
DEFAULT_LANGUAGE = "en"

_language: str | None = None

#: 「前置き: 値」の形を切り出す。前置きにはコロンを含めない。
_PREFIX_RE = re.compile(r"^(?P<prefix>[^:]+): (?P<rest>.+)$", re.DOTALL)


def detect_language() -> str:
    """環境変数から言語を推測する。

    `LANG=ja_JP.UTF-8` のような値から言語の部分だけを見る。
    ロケールが `C` や `POSIX` のときは英語にする (日本語を出すと
    端末やログで文字化けするため)。
    """
    for name in ("FROSTED_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if not value:
            continue
        base = value.split(".")[0].split("@")[0].strip()
        if base in ("", "C", "POSIX"):
            return DEFAULT_LANGUAGE
        return "ja" if base.startswith("ja") else DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def set_language(language: str | None) -> None:
    """言語を設定する。None なら環境変数から推測する。"""
    global _language
    if language is None:
        _language = detect_language()
        return
    normalized = language.strip().lower()
    if normalized not in SUPPORTED:
        raise ValueError(
            f"unsupported language: {language} (expected one of {', '.join(SUPPORTED)})"
        )
    _language = normalized


def get_language() -> str:
    global _language
    if _language is None:
        _language = detect_language()
    return _language


def translate_to_english(text: str) -> str:
    """英語にする。訳が無ければそのまま返す。"""
    exact = EN.get(text)
    if exact is not None:
        return exact

    match = _PREFIX_RE.match(text)
    if match is not None:
        prefix = PREFIXES.get(match.group("prefix"))
        if prefix is not None:
            return f"{prefix} {match.group('rest')}"

    for pattern, replacement in PATTERNS:
        if pattern.search(text):
            return pattern.sub(replacement, text)

    return text


def t(text: str, **kwargs: object) -> str:
    """文言を今の言語にして返す。

    kwargs を渡すと `{name}` のような場所を埋める。翻訳側にも同じ
    プレースホルダが要る (テストで確認している)。
    """
    result = text if get_language() == "ja" else translate_to_english(text)
    if not kwargs:
        return result
    try:
        return result.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # 訳のプレースホルダが食い違っている。表示は崩れるが、
        # ここで例外を投げるとビルド中に落ちてしまうので原文を返す。
        return text


def untranslated(text: str) -> bool:
    """その原文に英訳が用意されているか (テストとデバッグ用)。"""
    if text in EN:
        return False
    match = _PREFIX_RE.match(text)
    if match is not None and match.group("prefix") in PREFIXES:
        return False
    return not any(pattern.search(text) for pattern, _ in PATTERNS)

def t_block(text: str) -> str:
    """複数行の文書を 1 行ずつ訳す。

    生成するファイルや、プリセットが埋め込むスクリプトの中身に使う。
    利用者が書いた内容 (レシピの files.write など) には**使わない**。
    持ち込んだファイルの中身は、そのまま入るのが当然だから。
    """
    if get_language() == "ja":
        return text
    return chr(10).join(t_line(line) for line in text.split(chr(10)))


def t_line(line: str) -> str:
    """生成するファイルの中身を 1 行ずつ訳す。

    生成物はコメントもシェルの行も「1 行 = 1 単位」で書いてあるので、
    行で引けば十分に効く。

    インデントされた行は、まず行そのままで引き、無ければインデントを
    外した形で引いてからインデントを付け直す。こうしておくと、
    カタログ側にインデント込みの鍵を書かなくて済み、字下げを変えても
    訳が外れない。

    PREFIXES は使わない。行にはシェルの引用符やインデントが付いていて
    「前置き: 値」の形にたまたま当たることがあり、意図しない置換が起きうる。
    """
    if get_language() == "ja":
        return line
    exact = EN.get(line)
    if exact is not None:
        return exact

    stripped = line.strip()
    if stripped and stripped != line:
        translated = EN.get(stripped)
        if translated is not None:
            indent = line[: len(line) - len(line.lstrip())]
            return indent + translated

    for pattern, replacement in PATTERNS:
        if pattern.search(line):
            return pattern.sub(replacement, line)
    return line
