"""ドキュメントの壊れやすさを減らすためのテスト。

README と FEATURES に載せた TOML の例が構文エラーになっていないこと、
日英の README から機能一覧へリンクされていることを確認する。
"""

from __future__ import annotations

import re
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.ja.md",
    REPO_ROOT / "FEATURES.md",
    REPO_ROOT / "FEATURES.ja.md",
)

TOML_BLOCK = re.compile(r"```toml\n(.*?)```", re.DOTALL)


class DocsTest(unittest.TestCase):
    def test_toml_examples_parse(self) -> None:
        for path in DOCS:
            text = path.read_text(encoding="utf-8")
            blocks = TOML_BLOCK.findall(text)
            for index, block in enumerate(blocks, 1):
                with self.subTest(path=path.name, block=index):
                    try:
                        tomllib.loads(block)
                    except tomllib.TOMLDecodeError as exc:
                        self.fail(f"{path.name} の TOML 例 {index} が壊れています: {exc}")

    def test_readmes_link_to_the_feature_overview(self) -> None:
        english = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        japanese = (REPO_ROOT / "README.ja.md").read_text(encoding="utf-8")
        self.assertIn("FEATURES.md", english)
        self.assertIn("FEATURES.ja.md", japanese)

    def test_feature_overviews_link_to_each_other(self) -> None:
        english = (REPO_ROOT / "FEATURES.md").read_text(encoding="utf-8")
        japanese = (REPO_ROOT / "FEATURES.ja.md").read_text(encoding="utf-8")
        self.assertIn("FEATURES.ja.md", english)
        self.assertIn("FEATURES.md", japanese)


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    unittest.main()
