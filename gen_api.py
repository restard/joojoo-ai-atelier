#!/usr/bin/env python3
"""
Minimal local generation API for Custom GPT / Action prototyping.

Endpoints:
  GET  /health
  GET  /openapi.json
  GET  /generate-smoke
  POST /generate

POST /generate accepts the same deck JSON shape as build_deck.py, saves a PPTX
file locally, and returns JSON metadata. This is intentionally stdlib-only so
the thin E2E can run without adding a web framework yet.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import argparse
import json
import os
import re
import tempfile
import traceback

from build_deck import build_deck


ROOT_DIR = os.path.dirname(__file__)
DEFAULT_HOST = os.environ.get("HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT", "8787"))
BACKGROUND_TYPES = ["cover", "statement", "cta", "list", "person", "multi_image"]
DEMO_COLORS = {
    "terracotta": {
        "base": (196, 108, 80),
        "accent": (64, 99, 84),
        "light": (249, 238, 222),
    },
    "cream": {
        "base": (246, 238, 222),
        "accent": (183, 95, 73),
        "light": (78, 67, 56),
    },
    "deep_green": {
        "base": (51, 88, 75),
        "accent": (224, 137, 94),
        "light": (247, 238, 222),
    },
}

SMOKE_DECK = {
    "deck_title": "action_smoke_test",
    "color": "terracotta",
    "slides": [
        {
            "type": "statement",
            "color": "deep_green",
            "content": {
                "eyebrow": "Action test",
                "lines": ["接続テスト", "PPTX生成"],
            },
        }
    ],
}


def safe_filename(value):
    name = re.sub(r"[^\w\-一-龥ぁ-んァ-ンー]+", "_", value or "deck", flags=re.UNICODE)
    return name.strip("_") or "deck"


def ensure_demo_backgrounds():
    """Create public-safe placeholder backgrounds when deployed without customer assets."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return

    for color, palette in DEMO_COLORS.items():
        color_dir = os.path.join(ROOT_DIR, "backgrounds", color)
        os.makedirs(color_dir, exist_ok=True)
        for index, slide_type in enumerate(BACKGROUND_TYPES):
            path = os.path.join(color_dir, f"{slide_type}.png")
            if os.path.exists(path):
                continue

            width, height = 1920, 1080
            base = Image.new("RGB", (width, height), palette["base"])
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            for y in range(0, height, 12):
                alpha = int(18 + 32 * y / height)
                draw.line((0, y, width, y + 180), fill=(*palette["light"], alpha), width=3)

            offset = index * 90
            draw.ellipse(
                (width - 620 - offset, 120 + offset // 3, width + 180, 880 + offset // 3),
                fill=(*palette["accent"], 80),
            )
            draw.ellipse(
                (-260 + offset // 2, height - 520, 520 + offset // 2, height + 220),
                fill=(*palette["light"], 72),
            )
            draw.rounded_rectangle(
                (120, 120, width - 120, height - 120),
                radius=48,
                outline=(*palette["light"], 90),
                width=4,
            )
            overlay = overlay.filter(ImageFilter.GaussianBlur(0.4))
            Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB").save(path, quality=95)


def openapi_schema(host, port, public_url=None):
    base_url = public_url or f"http://{host}:{port}"
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "genDeck PPTX Generator",
            "version": "0.1.0",
            "description": "Generate a PPTX from a deck JSON spec.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/generate-smoke": {
                "get": {
                    "operationId": "generateSmokeDeck",
                    "summary": "Generate a smoke-test PowerPoint deck",
                    "description": "Generates a fixed one-slide PPTX for Custom GPT Action connectivity testing and returns JSON metadata.",
                    "responses": {
                        "200": {
                            "description": "Generation result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["ok", "filename", "relative_path", "size_bytes"],
                                        "properties": {
                                            "ok": {"type": "boolean"},
                                            "filename": {"type": "string"},
                                            "relative_path": {"type": "string"},
                                            "size_bytes": {"type": "integer"},
                                            "message": {"type": "string"},
                                        },
                                        "additionalProperties": True,
                                    }
                                }
                            },
                        },
                        "500": {"description": "Generation failed"},
                    },
                }
            },
            "/generate": {
                "post": {
                    "operationId": "generateDeck",
                    "summary": "Generate a PowerPoint deck",
                    "description": "Accepts a deck JSON string, saves a PPTX on the API server, and returns JSON metadata.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["deck_json"],
                                    "properties": {
                                        "deck_json": {
                                            "type": "string",
                                            "description": "A JSON string containing deck_title, color, and slides.",
                                        },
                                    },
                                    "additionalProperties": False,
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Generation result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["ok", "filename", "relative_path", "size_bytes"],
                                        "properties": {
                                            "ok": {"type": "boolean"},
                                            "filename": {"type": "string"},
                                            "relative_path": {"type": "string"},
                                            "size_bytes": {"type": "integer"},
                                            "message": {"type": "string"},
                                        },
                                        "additionalProperties": True,
                                    }
                                }
                            },
                        },
                        "400": {"description": "Invalid deck spec"},
                        "500": {"description": "Generation failed"},
                    },
                }
            },
        },
    }


class GenDeckHandler(BaseHTTPRequestHandler):
    server_version = "genDeck/0.1"
    protocol_version = "HTTP/1.1"

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _send_error_json(self, status, message, detail=None):
        payload = {"ok": False, "error": message}
        if detail:
            payload["detail"] = detail
        self._send_json(status, payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"ok": True})
            return
        if path == "/openapi.json":
            public_url = self.server.public_url
            if not public_url:
                forwarded_proto = self.headers.get("X-Forwarded-Proto")
                host = self.headers.get("Host")
                if forwarded_proto and host:
                    public_url = f"{forwarded_proto}://{host}"
            self._send_json(
                200,
                openapi_schema(
                    self.server.host,
                    self.server.server_port,
                    public_url,
                ),
            )
            return
        if path == "/generate-smoke":
            self._generate(SMOKE_DECK)
            return
        self._send_error_json(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/generate":
            self._send_error_json(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self._send_error_json(400, "Request body is required")
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                self._send_error_json(400, "Deck spec must be a JSON object")
                return
            if isinstance(payload.get("deck_json"), str):
                payload = json.loads(payload["deck_json"])
                if not isinstance(payload, dict):
                    self._send_error_json(400, "deck_json must decode to a JSON object")
                    return
            if not payload.get("deck_title") or not isinstance(payload.get("slides"), list):
                self._send_error_json(400, "deck_title and slides are required")
                return

            self._generate(payload)
        except json.JSONDecodeError as exc:
            self._send_error_json(400, "Invalid JSON", str(exc))
        except Exception as exc:
            traceback.print_exc()
            self._send_error_json(500, "Generation failed", str(exc))

    def _generate(self, payload):
        try:
            ensure_demo_backgrounds()
            title = safe_filename(payload.get("deck_title"))
            out_dir = os.path.join(ROOT_DIR, "dist", "api")
            work_dir = os.path.join(ROOT_DIR, "_slides", "api", title)
            os.makedirs(out_dir, exist_ok=True)
            os.makedirs(work_dir, exist_ok=True)
            output_pptx = os.path.join(out_dir, f"{title}.pptx")

            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                spec_path = f.name
            try:
                build_deck(
                    spec_path,
                    pool_dir=os.path.join(ROOT_DIR, "backgrounds"),
                    output_pptx=output_pptx,
                    work_dir=work_dir,
                    color=payload.get("color", "terracotta"),
                )
            finally:
                os.unlink(spec_path)

            filename = os.path.basename(output_pptx)
            self._send_json(
                200,
                {
                    "ok": True,
                    "filename": filename,
                    "relative_path": os.path.join("dist", "api", filename),
                    "size_bytes": os.path.getsize(output_pptx),
                    "message": "PPTX generated and saved on the API server.",
                },
            )
        except Exception as exc:
            traceback.print_exc()
            self._send_error_json(500, "Generation failed", str(exc))

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--public-url",
        default=os.environ.get("PUBLIC_URL"),
        help="HTTPS URL exposed by ngrok or another tunnel. Used in /openapi.json servers[0].url.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), GenDeckHandler)
    server.host = args.host
    server.public_url = args.public_url.rstrip("/") if args.public_url else None
    print(f"genDeck API listening on http://{args.host}:{args.port}")
    if server.public_url:
        print(f"Public URL: {server.public_url}")
        print(f"OpenAPI schema for Action: {server.public_url}/openapi.json")
    else:
        print(f"OpenAPI schema: http://{args.host}:{args.port}/openapi.json")
    server.serve_forever()


if __name__ == "__main__":
    main()
