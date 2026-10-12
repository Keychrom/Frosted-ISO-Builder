"""このツールが投げる例外。

「何が起きたか」と「どうすればいいか (hint)」を分けて持たせているのは、
CLI 側で必ず両方を表示したいから。利用者は Debian 上でこのツールを走らせる
ことが多く、エラーの原因がレシピにあるのか環境にあるのかが分かりにくい。
"""

from __future__ import annotations

from .i18n import t


class FrostedError(Exception):
    """基底例外。メッセージに加えて対処法のヒントを持てる。"""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class RecipeError(FrostedError):
    """レシピファイルの読み込み・解釈・検証に失敗した。"""


class PreflightError(FrostedError):
    """ビルド環境の前提条件を満たしていない。"""


class BuildError(FrostedError):
    """live-build の実行、または生成物の検証に失敗した。"""


class UserAbort(FrostedError):
    """利用者が操作を中断した (Ctrl-C / EOF など)。"""

    def __init__(self, message: str | None = None) -> None:
        # 既定値は呼び出し時に訳す。既定引数に書くと import 時に
        # 固定されてしまい、言語を切り替えても反映されない。
        super().__init__(message or t("操作を中断しました。"))
