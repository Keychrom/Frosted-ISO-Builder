"""GUI の HTTP API のテスト。

ブラウザの JavaScript はここでは動かさず、サーバーとの契約
(認証、読み書き、検証、生成) を確認する。画面の見た目は
`frosted gui` を起動して手で確認する。
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frosted.gui.schema import SECTIONS, UI_STRINGS, schema_for  # noqa: E402
from frosted.gui.server import create_server  # noqa: E402
from frosted.recipe import Recipe  # noqa: E402

RECIPE = {
    "version": 1,
    "iso": {"name": "citest"},
}


class GuiServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.recipe_path = self.root / "citest.toml"
        self.recipe_path.write_text(
            'version = 1\n\n[iso]\nname = "citest"\n', encoding="utf-8"
        )
        self.server = create_server(
            port=0,
            initial_path=self.recipe_path,
            lang="ja",
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    # -- helpers ------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        token: bool = True,
        content_type: str = "application/json",
        host: str | None = None,
    ) -> tuple[int, dict | bytes]:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            method=method,
        )
        if body is not None:
            request.add_header("Content-Type", content_type)
        if token:
            request.add_header("X-Frosted-Token", self.server.token)
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                if response.headers.get_content_type() == "application/json":
                    return response.status, json.loads(raw)
                return response.status, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    def _post(self, name: str, payload: dict | None = None, **kwargs):
        return self._request("POST", f"/api/{name}", payload=payload or {}, **kwargs)

    # -- static and security ------------------------------------------

    def test_index_contains_the_token_and_assets(self) -> None:
        status, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn('name="frosted-token"', text)
        self.assertIn(self.server.token, text)
        self.assertIn("style.css?v=", text)
        self.assertIn("app.js?v=", text)
        self.assertNotIn("__FROSTED_", text)

        for asset in ("/app.js", "/style.css", "/favicon.svg"):
            with self.subTest(asset=asset):
                status, _body = self._request("GET", asset)
                self.assertEqual(status, 200)

    def test_unknown_static_path_is_404(self) -> None:
        status, _body = self._request("GET", "/nope")
        self.assertEqual(status, 404)

    def test_token_is_required(self) -> None:
        status, body = self._post("bootstrap", token=False)
        self.assertEqual(status, 401)
        self.assertFalse(body["ok"])

    def test_foreign_host_header_is_rejected(self) -> None:
        status, body = self._post("bootstrap", host="evil.example")
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_wrong_content_type_is_rejected(self) -> None:
        status, _body = self._post(
            "bootstrap", content_type="text/plain"
        )
        self.assertEqual(status, 415)

    # -- bootstrap and validation -------------------------------------

    def test_bootstrap_returns_the_recipe_and_schema(self) -> None:
        status, data = self._post("bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["recipe"]["iso"]["name"], "citest")
        self.assertEqual(data["path"], str(self.recipe_path))
        self.assertGreater(len(data["sections"]), 5)
        self.assertGreater(len(data["presets"]), 3)
        self.assertIn("save", data["strings"])
        self.assertIn("toml", data)

    def test_validate_reports_errors_without_saving(self) -> None:
        bad = {"version": 1, "iso": {"name": "Bad Name"}}
        before = self.recipe_path.read_text(encoding="utf-8")
        status, data = self._post(
            "validate", {"path": str(self.recipe_path), "recipe": bad}
        )
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertTrue(
            any(issue["where"] == "iso.name" for issue in data["issues"])
        )
        self.assertEqual(self.recipe_path.read_text(encoding="utf-8"), before)

    def test_validate_returns_lb_arguments(self) -> None:
        status, data = self._post(
            "validate", {"path": str(self.recipe_path), "recipe": RECIPE}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("--distribution", data["summary"]["lb_args"])
        self.assertIn("boot=live", data["summary"]["bootappend"])

    # -- save ---------------------------------------------------------

    def test_save_writes_the_recipe_and_creates_a_backup(self) -> None:
        status, data = self._post(
            "save", {"path": str(self.recipe_path), "recipe": RECIPE}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(self.recipe_path.is_file())
        self.assertIn("[iso]", self.recipe_path.read_text(encoding="utf-8"))
        self.assertTrue(Path(data["backup"]).is_file())

    def test_save_rejects_an_invalid_recipe(self) -> None:
        before = self.recipe_path.read_text(encoding="utf-8")
        status, data = self._post(
            "save",
            {
                "path": str(self.recipe_path),
                "recipe": {"version": 1, "iso": {"name": "Bad Name"}},
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(self.recipe_path.read_text(encoding="utf-8"), before)

    def test_form_save_warns_when_comments_would_be_lost(self) -> None:
        self.recipe_path.write_text(
            "# this comment would be lost\n"
            "version = 1\n\n"
            "[iso]\n"
            'name = "citest"\n',
            encoding="utf-8",
        )
        status, data = self._post(
            "save", {"path": str(self.recipe_path), "recipe": RECIPE}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(
            any(
                "コメント" in issue["message"] or "comment" in issue["message"]
                for issue in data["issues"]
            ),
            data["issues"],
        )

    def test_parse_and_save_raw_preserve_comments(self) -> None:
        text = (
            "# keep this comment\n"
            "version = 1\n\n"
            "[iso]\n"
            'name = "rawtest"\n'
        )
        status, data = self._post(
            "parse", {"path": str(self.recipe_path), "text": text}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["recipe"]["iso"]["name"], "rawtest")

        status, data = self._post(
            "save_raw", {"path": str(self.recipe_path), "text": text}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn(
            "# keep this comment",
            self.recipe_path.read_text(encoding="utf-8"),
        )

    # -- generate and doctor ------------------------------------------

    def test_generate_writes_the_live_build_tree(self) -> None:
        status, data = self._post(
            "generate", {"path": str(self.recipe_path), "recipe": RECIPE}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("auto/config", data["created"])
        self.assertTrue((self.root / "build" / "auto" / "config").is_file())

    def test_doctor_returns_checks(self) -> None:
        status, data = self._post(
            "doctor",
            {
                "path": str(self.recipe_path),
                "recipe": RECIPE,
                "network": False,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["checks"])
        self.assertIn("status", data["checks"][0])

    # -- new and localisation -----------------------------------------

    def test_new_recipe_can_apply_a_preset(self) -> None:
        status, data = self._post(
            "new", {"name": "kiosk-test", "preset": "kiosk"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["recipe"]["desktop"]["environment"], "xfce")
        self.assertFalse(data["recipe"]["ssh"]["enable_server"])
        self.assertFalse(data["recipe"]["user"]["sudo"])

    def test_english_ui_strings_and_labels(self) -> None:
        self.server.lang = "en"
        try:
            status, data = self._post("bootstrap")
        finally:
            self.server.lang = "ja"
        self.assertEqual(status, 200)
        self.assertEqual(data["strings"]["save"], "Save")
        iso = data["sections"][0]
        self.assertEqual(iso["label"], "ISO")
        self.assertEqual(iso["fields"][0]["label"], "Name")


class GuiSchemaTest(unittest.TestCase):
    def test_every_field_path_exists_on_the_recipe(self) -> None:
        recipe = Recipe()
        for section in SECTIONS:
            for field in section.fields:
                with self.subTest(path=field.path):
                    current = recipe
                    for part in field.path.split("."):
                        self.assertTrue(
                            hasattr(current, part),
                            f"{field.path} の {part} が Recipe にありません",
                        )
                        current = getattr(current, part)

    def test_schema_is_complete_in_both_languages(self) -> None:
        for lang in ("ja", "en"):
            sections = schema_for(lang)
            self.assertEqual(len(sections), len(SECTIONS))
            for section in sections:
                self.assertTrue(section["label"])
                for field in section["fields"]:
                    self.assertTrue(field["label"])
                    if field["kind"] == "select":
                        self.assertTrue(field["options"], field["path"])

    def test_ui_strings_have_both_languages(self) -> None:
        for key, (japanese, english) in UI_STRINGS.items():
            with self.subTest(key=key):
                self.assertTrue(japanese)
                self.assertTrue(english)


if __name__ == "__main__":
    unittest.main()
