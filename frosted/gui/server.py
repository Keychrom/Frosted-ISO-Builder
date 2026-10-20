"""`frosted gui` のローカル Web サーバー。

ブラウザでレシピを編集し、検証・設定生成・環境診断まで行う。
ビルド自体は root と Debian が必要なので、この段階では実行せず
コマンドを表示するだけにしている。

外部依存は無い (標準ライブラリの http.server を使う)。127.0.0.1 にだけ
バインドし、ランダムなトークンと Host ヘッダの検証で、同じマシンの
ブラウザから来た正規の画面以外は操作できないようにする。
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import tempfile
import tomllib
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .. import __version__
from ..backend.livebuild import (
    build_bootappend,
    build_failsafe_append,
    build_lb_argv,
    generate,
)
from ..catalog import DESKTOPS, apply_preset
from ..errors import BuildError, RecipeError
from ..i18n import get_language
from ..preflight import run as run_preflight
from ..recipe import Issue, Recipe, RecipeProblems
from .schema import localize, presets_for, schema_for, strings_for

#: 1 リクエストで受け付ける最大サイズ。レシピは数 KB なので十分。
MAX_BODY = 4 * 1024 * 1024

WEB_ROOT = Path(__file__).resolve().parent / "web"


class GuiServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows の SO_REUSEADDR は「同じポートへの複数バインド」を許してしまい、
    # 既に別のサーバーが使っているポートでも起動できてしまう。その場合
    # ブラウザは先にいたサーバーに繋がるので、GUI が開かない。
    allow_reuse_address = os.name != "nt"

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        token: str,
        initial_path: Path | None,
        lang: str,
    ) -> None:
        super().__init__(address, handler)
        self.token = token
        self.initial_path = initial_path
        self.lang = lang


def create_server(
    *,
    port: int = 8765,
    initial_path: Path | None = None,
    lang: str | None = None,
) -> GuiServer:
    """サーバーを作る。port=0 なら OS に空きポートを選ばせる。"""
    if port < 0 or port > 65535:
        raise ValueError(f"invalid port: {port}")
    token = secrets.token_urlsafe(24)
    language = lang or get_language()
    ports = [0] if port == 0 else range(port, port + 20)
    last_error: OSError | None = None
    for candidate in ports:
        try:
            return GuiServer(
                ("127.0.0.1", candidate),
                GuiHandler,
                token=token,
                initial_path=initial_path,
                lang=language,
            )
        except OSError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise OSError("no port available")


def serve(
    initial_path: Path | None = None,
    *,
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """サーバーを起動して、Ctrl-C まで待つ。"""
    from .. import ui
    from ..i18n import t

    if port < 0 or port > 65535:
        raise BuildError(
            t("ポート番号が不正です: {port}", port=port),
            hint=t("0 から 65535 の範囲で指定してください。"),
        )

    if initial_path is not None:
        initial_path = initial_path.expanduser().resolve()
        if initial_path.suffix.lower() != ".toml" or not initial_path.is_file():
            raise BuildError(
                t("レシピが見つかりません: {path}", path=initial_path),
                hint=t(".toml ファイルのパスを指定してください。"),
            )

    server = create_server(port=port, initial_path=initial_path)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    ui.out(t("GUI を起動しました: {url}", url=url))
    ui.hint(t("終了するときは Ctrl-C を押してください。"))
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            ui.warn(t("ブラウザを開けませんでした。上の URL を開いてください。"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ui.out()
        ui.info(t("GUI を終了しました。"))
    finally:
        server.server_close()


class GuiHandler(BaseHTTPRequestHandler):
    server: GuiServer
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    # ルーティング
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_bytes(200, b"ok", "text/plain; charset=utf-8")
            return
        if path in ("/", "/index.html"):
            self._send_index()
            return
        static = {
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
        }
        target = static.get(path)
        if target is None:
            self._send_bytes(404, b"not found", "text/plain; charset=utf-8")
            return
        name, content_type = target
        source = WEB_ROOT / name
        if not source.is_file():
            self._send_bytes(404, b"not found", "text/plain; charset=utf-8")
            return
        self._send_bytes(200, source.read_bytes(), content_type)

    def do_POST(self) -> None:
        if not self._guard():
            return
        try:
            payload = self._read_json()
            route = self.path.split("?", 1)[0]
            name = route.removeprefix("/api/")
            handler = {
                "bootstrap": self._bootstrap,
                "load": self._load,
                "new": self._new,
                "save": self._save,
                "save_raw": self._save_raw,
                "parse": self._parse,
                "validate": self._validate,
                "render": self._render,
                "generate": self._generate,
                "doctor": self._doctor,
            }.get(name)
            if handler is None:
                self._send_json(404, {"ok": False, "message": "not found"})
                return
            handler(payload)
        except RecipeProblems as exc:
            self._send_json(
                400,
                {
                    "ok": False,
                    "message": self._m(
                        "レシピにエラーがあります。",
                        "The recipe has errors.",
                    ),
                    "issues": self._issues(exc.issues),
                },
            )
        except RecipeError as exc:
            self._send_json(
                400,
                {
                    "ok": False,
                    "message": localize(str(exc), self.server.lang),
                    "hint": localize(exc.hint or "", self.server.lang),
                    "issues": [],
                },
            )
        except BuildError as exc:
            self._send_json(
                400,
                {
                    "ok": False,
                    "message": localize(str(exc), self.server.lang),
                    "hint": localize(exc.hint or "", self.server.lang),
                    "issues": [],
                },
            )
        except ValueError as exc:
            self._send_json(
                400,
                {"ok": False, "message": str(exc), "issues": []},
            )
        except OSError as exc:
            self._send_json(
                500,
                {
                    "ok": False,
                    "message": self._m(
                        f"ファイル操作に失敗しました: {exc}",
                        f"File operation failed: {exc}",
                    ),
                    "issues": [],
                },
            )
        except Exception:
            traceback.print_exc()
            self._send_json(
                500,
                {
                    "ok": False,
                    "message": self._m(
                        "サーバー内部でエラーが発生しました。",
                        "Internal server error.",
                    ),
                    "issues": [],
                },
            )

    def do_OPTIONS(self) -> None:
        # CORS は許可しない。クロスオリジンの fetch はここで止まる。
        self._send_bytes(405, b"method not allowed", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        # 既定のアクセスログは画面を埋めるので出さない。
        return

    # ------------------------------------------------------------------
    # リクエストの検証
    # ------------------------------------------------------------------

    def _guard(self) -> bool:
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        allowed = {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
        }
        if host not in allowed:
            self._send_json(403, {"ok": False, "message": "forbidden host"})
            return False

        token = self.headers.get("X-Frosted-Token", "")
        if not secrets.compare_digest(token, self.server.token):
            self._send_json(401, {"ok": False, "message": "invalid token"})
            return False

        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            self._send_json(
                415,
                {"ok": False, "message": "Content-Type must be application/json"},
            )
            return False

        length = self.headers.get("Content-Length")
        if length is None:
            self._send_json(411, {"ok": False, "message": "Content-Length required"})
            return False
        try:
            size = int(length)
        except ValueError:
            self._send_json(400, {"ok": False, "message": "invalid Content-Length"})
            return False
        if size < 0 or size > MAX_BODY:
            self._send_json(413, {"ok": False, "message": "request too large"})
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size) if size else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    # ------------------------------------------------------------------
    # レスポンス
    # ------------------------------------------------------------------

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_index(self) -> None:
        source = WEB_ROOT / "index.html"
        if not source.is_file():
            self._send_bytes(500, b"index.html is missing", "text/plain; charset=utf-8")
            return
        text = source.read_text(encoding="utf-8")
        text = text.replace("__FROSTED_TOKEN__", self.server.token)
        text = text.replace("__FROSTED_LANG__", self.server.lang)
        text = text.replace("__FROSTED_TITLE__", "Frosted ISO Builder")
        # 起動ごとに変わる値で CSS/JS のキャッシュを確実に更新する。
        text = text.replace("__FROSTED_ASSET_VERSION__", self.server.token[:12])
        self._send_bytes(200, text.encode("utf-8"), "text/html; charset=utf-8")

    # ------------------------------------------------------------------
    # エンドポイント
    # ------------------------------------------------------------------

    def _bootstrap(self, payload: dict[str, Any]) -> None:
        path = self.server.initial_path
        raw: str | None = None
        if path is not None:
            recipe = Recipe.load(path)
            raw = path.read_text(encoding="utf-8-sig")
        else:
            path = Path.cwd() / "mylinux.toml"
            recipe = Recipe()
            recipe.iso.name = "mylinux"
            recipe.path = path
        self._send_json(
            200,
            {
                "ok": True,
                "version": __version__,
                "lang": self.server.lang,
                "strings": strings_for(self.server.lang),
                "sections": schema_for(self.server.lang),
                "presets": presets_for(self.server.lang),
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": raw if raw is not None else recipe.dumps(),
                "issues": self._issues(recipe.warnings),
                "summary": self._summary(recipe, path),
            },
        )

    def _load(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=True)
        recipe = Recipe.load(path)
        raw = path.read_text(encoding="utf-8-sig")
        self._send_json(
            200,
            {
                "ok": True,
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": raw,
                "issues": self._issues(recipe.warnings),
                "summary": self._summary(recipe, path),
            },
        )

    def _new(self, payload: dict[str, Any]) -> None:
        name = payload.get("name", "mylinux")
        if not isinstance(name, str) or not name.strip():
            name = "mylinux"
        name = name.strip()
        recipe = Recipe()
        recipe.iso.name = name
        preset = payload.get("preset")
        if preset:
            if not isinstance(preset, str):
                raise ValueError("invalid preset")
            try:
                apply_preset(recipe, preset)
            except KeyError as exc:
                raise ValueError(f"unknown preset: {preset}") from exc
        path = Path.cwd() / f"{name}.toml"
        recipe = Recipe.from_dict(recipe.to_dict(), path=path)
        self._send_json(
            200,
            {
                "ok": True,
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": recipe.dumps(),
                "issues": self._issues(recipe.warnings),
                "summary": self._summary(recipe, path),
            },
        )

    def _validate(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        data = payload.get("recipe")
        if not isinstance(data, dict):
            raise ValueError(self._m("レシピの内容がありません。", "No recipe data."))
        try:
            recipe = Recipe.from_dict(data, path=path)
        except RecipeProblems as exc:
            self._send_json(
                200,
                {
                    "ok": False,
                    "issues": self._issues(exc.issues),
                    "summary": None,
                },
            )
            return
        self._send_json(
            200,
            {
                "ok": True,
                "issues": self._issues(recipe.warnings),
                "toml": recipe.dumps(),
                "summary": self._summary(recipe, path),
            },
        )

    def _render(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        recipe = self._recipe(payload, path)
        self._send_json(
            200,
            {
                "ok": True,
                "toml": recipe.dumps(),
                "summary": self._summary(recipe, path),
            },
        )

    def _parse(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        text = payload.get("text")
        if not isinstance(text, str):
            raise ValueError(self._m("TOML の内容がありません。", "No TOML text."))
        text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(
                self._m(
                    f"TOML の構文エラー: {exc}",
                    f"TOML syntax error: {exc}",
                )
            ) from exc
        recipe = Recipe.from_dict(data, path=path)
        self._send_json(
            200,
            {
                "ok": True,
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": text,
                "issues": self._issues(recipe.warnings),
                "summary": self._summary(recipe, path),
            },
        )

    def _save(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        recipe = self._recipe(payload, path)
        existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        backup = self._backup(path)
        text = recipe.dumps()
        _atomic_write(path, text)
        issues = list(recipe.warnings)
        if _has_comments(existing):
            issues.append(
                Issue(
                    "warning",
                    "",
                    self._m(
                        "フォームから保存すると TOML は正規化され、コメントは失われます。",
                        "Saving from the form normalizes the TOML and loses comments.",
                    ),
                )
            )
        self._send_json(
            200,
            {
                "ok": True,
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": text,
                "backup": str(backup) if backup else "",
                "issues": self._issues(issues),
                "summary": self._summary(recipe, path),
            },
        )

    def _save_raw(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        text = payload.get("text")
        if not isinstance(text, str):
            raise ValueError(self._m("TOML の内容がありません。", "No TOML text."))
        text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(
                self._m(
                    f"TOML の構文エラー: {exc}",
                    f"TOML syntax error: {exc}",
                )
            ) from exc
        recipe = Recipe.from_dict(data, path=path)
        backup = self._backup(path)
        if not text.endswith("\n"):
            text += "\n"
        _atomic_write(path, text)
        self._send_json(
            200,
            {
                "ok": True,
                "recipe": recipe.to_dict(),
                "path": str(path),
                "toml": text,
                "backup": str(backup) if backup else "",
                "issues": self._issues(recipe.warnings),
                "summary": self._summary(recipe, path),
            },
        )

    def _generate(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        recipe = self._recipe(payload, path)
        result = generate(recipe)
        created = sorted(
            {
                _relative_to(item, result.workdir)
                for item in result.created
            }
        )
        self._send_json(
            200,
            {
                "ok": True,
                "created": created,
                "warnings": [
                    localize(warning, self.server.lang)
                    for warning in result.warnings
                ],
                "workdir": str(result.workdir),
                "issues": self._issues(recipe.warnings),
            },
        )

    def _doctor(self, payload: dict[str, Any]) -> None:
        path = self._recipe_path(payload.get("path"), must_exist=False)
        recipe = self._recipe(payload, path)
        report = run_preflight(
            recipe,
            require_root=False,
            check_network=bool(payload.get("network", False)),
        )
        checks = [
            {
                "name": localize(check.name, self.server.lang),
                "status": check.status,
                "detail": localize(check.detail, self.server.lang),
                "hint": localize(check.hint, self.server.lang),
            }
            for check in report.checks
        ]
        self._send_json(
            200,
            {
                "ok": True,
                "passed": report.passed,
                "checks": checks,
            },
        )

    # ------------------------------------------------------------------
    # 共通処理
    # ------------------------------------------------------------------

    def _recipe(self, payload: dict[str, Any], path: Path) -> Recipe:
        data = payload.get("recipe")
        if not isinstance(data, dict):
            raise ValueError(self._m("レシピの内容がありません。", "No recipe data."))
        return Recipe.from_dict(data, path=path)

    def _recipe_path(self, raw: object, *, must_exist: bool) -> Path:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                self._m("レシピのパスを指定してください。", "Specify a recipe path.")
            )
        path = Path(raw).expanduser()
        if path.suffix.lower() != ".toml":
            raise ValueError(
                self._m(
                    "レシピは .toml ファイルにしてください。",
                    "The recipe must be a .toml file.",
                )
            )
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if must_exist and not path.is_file():
            raise ValueError(
                self._m(
                    f"レシピが見つかりません: {path}",
                    f"Recipe not found: {path}",
                )
            )
        if path.exists() and not path.is_file():
            raise ValueError(
                self._m(
                    f"レシピがファイルではありません: {path}",
                    f"Recipe is not a file: {path}",
                )
            )
        return path

    def _backup(self, path: Path) -> Path | None:
        if not path.is_file():
            return None
        backup = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup)
        return backup

    def _issues(self, issues: list[Issue]) -> list[dict[str, Any]]:
        return [
            {
                "level": issue.level,
                "where": issue.where,
                "message": localize(issue.message, self.server.lang),
                "hint": localize(issue.hint, self.server.lang),
            }
            for issue in issues
        ]

    def _summary(self, recipe: Recipe, path: Path) -> dict[str, Any]:
        args, lb_warnings = build_lb_argv(recipe)
        quoted = shlex.quote(str(path))
        profile = DESKTOPS.get(recipe.desktop.environment)
        return {
            "name": recipe.iso.name,
            "output": recipe.iso.resolved_output(),
            "base": f"{recipe.iso.distribution} / {recipe.iso.architecture}",
            "desktop": (
                localize(profile.label, self.server.lang)
                if profile is not None
                else recipe.desktop.environment
            ),
            "workdir": str(recipe.workdir()),
            "bootappend": build_bootappend(recipe),
            "failsafe": build_failsafe_append(recipe),
            "lb_args": args,
            "warnings": [
                localize(warning, self.server.lang) for warning in lb_warnings
            ],
            "commands": {
                "build": f"sudo frosted build {quoted}",
                "test": f"frosted test {quoted}",
                "generate": f"frosted gen {quoted}",
                "doctor": f"frosted doctor {quoted}",
            },
        }

    def _m(self, ja: str, en: str) -> str:
        return en if self.server.lang == "en" else ja


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _has_comments(text: str) -> bool:
    return any(line.lstrip().startswith("#") for line in text.splitlines())


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
