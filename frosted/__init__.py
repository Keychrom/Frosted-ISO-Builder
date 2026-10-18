"""Frosted ISO Builder -- Debian Live ISO をかんたんに作るためのツール。

レシピファイル (TOML) に作りたいものだけを書き、live-build の複雑な設定は
このツールが全部組み立てる、というのが基本の考え方。
"""

__version__ = "0.1.1"

#: プロジェクト名。README や ISO のメタデータに出す。
PROJECT_NAME = "Frosted ISO Builder"

#: コマンド名。生成物のヘッダやエラーメッセージにも使う。
APP_NAME = "frosted"

#: 生成した設定ファイルに埋め込む署名。どのバージョンで作られた設定か分かるようにする。
GENERATED_BY = f"{APP_NAME} {__version__}"

#: ISO のメタデータに書き込む既定の作成者表記。
DEFAULT_PREPARER = f"{PROJECT_NAME} {__version__}"

__all__ = [
    "__version__",
    "PROJECT_NAME",
    "APP_NAME",
    "GENERATED_BY",
    "DEFAULT_PREPARER",
]
