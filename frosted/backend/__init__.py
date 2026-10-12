"""バックエンド (実際に ISO を組み立てる側)。

今のところ live-build だけ。将来 debootstrap 直叩きのバックエンドを足すなら
このパッケージにもう 1 ファイル増やす形になる。
"""

from .livebuild import GenerationResult, generate

__all__ = ["GenerationResult", "generate"]
