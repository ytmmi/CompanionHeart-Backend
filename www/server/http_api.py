"""HTTP 路由与请求处理。

GET 全部是幂等查询，用一张路由表；POST 有副作用，逐条列出便于阅读。
静态文件（index.html / css / js）由 SimpleHTTPRequestHandler 从 www/ 提供。
"""
from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .backups import list_backups, reset_to_example, restore_backup
from .config_io import get_all_keys, get_llm_port, update_keys
from .diagnostics import get_status, restart_agent, test_connection
from .jobs import get_job
from .paths import WWW_DIR, logger
from .plugins_install import install_plugin
from .plugins_registry import get_plugin_logs, get_plugins
from .plugins_runtime import start_plugin, stop_plugin, uninstall_plugin
from .ports import check_port
from .preview import tts_preview
from .schema import get_schema
from .voices import edge_voice_catalog, get_llm_models, get_tts_voices


class SettingsHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WWW_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    # ── GET ──
    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        routes = {
            "/api/settings/schema":      lambda: get_schema(),
            "/api/settings/keys":        lambda: get_all_keys(),
            "/api/settings/tts-voices":  lambda: {"voices": get_tts_voices()},
            "/api/settings/status":      lambda: get_status(),
            "/api/settings/backups":     lambda: list_backups(),
            "/api/settings/edge-voices": lambda: {"voices": edge_voice_catalog()},
            "/api/settings/llm-models":  lambda: get_llm_models(query.get("mode", ["openai"])[0]),
            "/api/settings/llm-port":    lambda: get_llm_port(),
            "/api/settings/check-port":  lambda: check_port(
                int(query.get("port", ["0"])[0]), query.get("module", [None])[0]),
            "/api/plugins":              lambda: get_plugins(),
            "/api/plugins/logs":         lambda: get_plugin_logs(
                query.get("name", [""])[0], int(query.get("tail", ["200"])[0])),
            "/api/plugins/job":          lambda: get_job(
                query.get("id", [""])[0], int(query.get("since", ["0"])[0])),
        }

        if path in routes:
            try:
                self._json(routes[path]())
            except Exception as e:
                logger.exception("GET %s 失败", path)
                self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
            return

        if path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()

    # ── POST ──
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = json.loads(self._body() or "{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "Invalid JSON"}, 400)
            return

        try:
            if path == "/api/settings/keys":
                self._json(update_keys(body))
            elif path == "/api/settings/test":
                self._json(test_connection(body.get("module", "")))
            elif path == "/api/settings/restore":
                self._json(restore_backup(body.get("module", ""), body.get("file", "")))
            elif path == "/api/settings/reset":
                self._json(reset_to_example(body.get("module", "")))
            elif path == "/api/settings/agent-restart":
                self._json(restart_agent())
            elif path == "/api/settings/tts-preview":
                audio, ctype, err = tts_preview(body)
                if err or not audio:
                    self._json({"ok": False, "error": err or "合成返回空音频"}, 502)
                else:
                    self._binary(audio, ctype)
            elif path == "/api/plugins/install":
                self._json(install_plugin(body))
            elif path == "/api/plugins/start":
                self._json(start_plugin(body))
            elif path == "/api/plugins/stop":
                self._json(stop_plugin(body))
            elif path == "/api/plugins/uninstall":
                self._json(uninstall_plugin(body))
            else:
                self._json({"error": "Not found"}, 404)
        except Exception as e:
            logger.exception("POST %s 失败", path)
            self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    # ── 辅助 ──
    def _body(self) -> str:
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n).decode("utf-8") if n > 0 else "{}"

    def _json(self, data, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _binary(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        logger.info("[%s] %s", self.client_address[0], fmt % args)
